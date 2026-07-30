#!/usr/bin/env python3
"""Capture a secret-free security snapshot from the retained Pigsty lab."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from common import (
    LabError,
    ensure_no_secret_material,
    patroni_list,
    pgbouncer_config,
    read_json,
    remote_json_psql,
    remote_root_program_json,
    utc_now,
    write_json,
)


POSTGRES_SECURITY_SQL = r"""
SELECT json_build_object(
  'schema', 'pg36-ch23-postgresql-security-v1',
  'identity', json_build_object(
    'server_version', current_setting('server_version'),
    'server_version_num', current_setting('server_version_num')::int,
    'cluster_name', current_setting('cluster_name'),
    'port', current_setting('port')::int,
    'in_recovery', pg_is_in_recovery(),
    'transaction_read_only',
      current_setting('transaction_read_only')::boolean
  ),
  'settings', (
    SELECT json_object_agg(name, setting ORDER BY name)
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'listen_addresses',
      'ssl',
      'ssl_ca_file',
      'ssl_cert_file',
      'ssl_key_file',
      'ssl_crl_file',
      'ssl_crl_dir',
      'ssl_min_protocol_version',
      'ssl_max_protocol_version',
      'password_encryption',
      'hba_file',
      'ident_file',
      'shared_preload_libraries',
      'session_preload_libraries',
      'log_destination',
      'logging_collector',
      'log_directory',
      'log_file_mode',
      'log_line_prefix',
      'log_connections',
      'log_disconnections',
      'log_statement',
      'log_min_duration_statement',
      'log_min_error_statement',
      'log_parameter_max_length',
      'log_parameter_max_length_on_error'
    ])
  ),
  'optional_settings', json_build_object(
    'auto_explain.log_parameter_max_length',
      current_setting('auto_explain.log_parameter_max_length', true),
    'pgaudit.log', current_setting('pgaudit.log', true),
    'pgaudit.log_parameter', current_setting('pgaudit.log_parameter', true)
  ),
  'hba_rules', (
    SELECT COALESCE(
      json_agg(
        json_build_object(
          'rule_number', rule_number,
          'file_name', file_name,
          'line_number', line_number,
          'type', type,
          'database', database,
          'user_name', user_name,
          'address', address,
          'netmask', netmask,
          'auth_method', auth_method,
          'options', options,
          'error', error
        )
        ORDER BY rule_number NULLS LAST, line_number
      ),
      '[]'::json
    )
    FROM pg_hba_file_rules
  ),
  'hba_parse_errors', (
    SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL
  ),
  'extensions', (
    SELECT COALESCE(
      json_agg(
        json_build_object(
          'name', available.name,
          'default_version', available.default_version,
          'installed_version', installed.extversion
        )
        ORDER BY available.name
      ),
      '[]'::json
    )
    FROM pg_available_extensions AS available
    LEFT JOIN pg_extension AS installed
      ON installed.extname = available.name
    WHERE available.name IN ('pgaudit', 'set_user', 'credcheck')
  ),
  'roles', (
    SELECT COALESCE(
      json_agg(
        json_build_object(
          'name', rolname,
          'login', rolcanlogin,
          'superuser', rolsuper,
          'create_role', rolcreaterole,
          'create_db', rolcreatedb,
          'replication', rolreplication,
          'bypass_rls', rolbypassrls,
          'inherit_default', rolinherit,
          'connection_limit', rolconnlimit,
          'password_present',
            EXISTS (
              SELECT 1
              FROM pg_authid AS auth
              WHERE auth.oid = roles.oid
                AND auth.rolpassword IS NOT NULL
            ),
          'comment', shobj_description(roles.oid, 'pg_authid')
        )
        ORDER BY rolname
      ),
      '[]'::json
    )
    FROM pg_roles AS roles
    WHERE rolname IN (
      'postgres',
      'dbuser_dba',
      'dbuser_monitor',
      'replicator',
      'test',
      'dbrole_readonly',
      'dbrole_readwrite',
      'dbrole_admin',
      'pg36_ch23_owner',
      'pg36_ch23_runtime',
      'pg36_ch23_readonly',
      'pg36_ch23_migrate',
      'pg36_ch23_rotate'
    )
  ),
  'memberships', (
    SELECT COALESCE(
      json_agg(
        json_build_object(
          'role', role_role.rolname,
          'member', member_role.rolname,
          'grantor', grantor_role.rolname,
          'admin', membership.admin_option,
          'inherit', membership.inherit_option,
          'set', membership.set_option
        )
        ORDER BY role_role.rolname, member_role.rolname
      ),
      '[]'::json
    )
    FROM pg_auth_members AS membership
    JOIN pg_roles AS role_role ON role_role.oid = membership.roleid
    JOIN pg_roles AS member_role ON member_role.oid = membership.member
    JOIN pg_roles AS grantor_role ON grantor_role.oid = membership.grantor
    WHERE role_role.rolname LIKE 'pg36_ch23%'
       OR member_role.rolname LIKE 'pg36_ch23%'
       OR member_role.rolname = 'test'
  )
);
"""


HOST_PROJECTION = r"""
import hashlib
import json
import os
import pathlib
import re
import ssl
import stat
import subprocess


def metadata(path):
    value = pathlib.Path(path)
    if not value.exists():
        return {"exists": False}
    info = value.stat()
    return {
        "exists": True,
        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "is_regular": value.is_file(),
        "is_directory": value.is_dir(),
    }


def parse_ini(path):
    selected = {}
    allowed = {
        "listen_addr",
        "listen_port",
        "auth_type",
        "auth_hba_file",
        "pool_mode",
        "server_tls_sslmode",
        "client_tls_sslmode",
        "server_reset_query",
        "server_reset_query_always",
        "max_client_conn",
        "default_pool_size",
        "reserve_pool_size",
        "reserve_pool_timeout",
        "query_wait_timeout",
        "max_prepared_statements",
    }
    section = None
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "pgbouncer" and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in allowed:
                selected[key] = value
    return selected


def parse_hba(path):
    rules = []
    for line_number, raw in enumerate(
        pathlib.Path(path).read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if fields[0] == "local":
            rule = {
                "line_number": line_number,
                "type": fields[0],
                "database": fields[1],
                "user": fields[2],
                "address": None,
                "auth_method": fields[3],
            }
        else:
            rule = {
                "line_number": line_number,
                "type": fields[0],
                "database": fields[1],
                "user": fields[2],
                "address": fields[3],
                "auth_method": fields[4],
            }
        rules.append(rule)
    return rules


def subject_map(parts):
    result = {}
    for group in parts:
        for key, value in group:
            result.setdefault(key, []).append(value)
    return result


certificate_path = "/pg/cert/server.crt"
decoded = ssl._ssl._test_decode_cert(certificate_path)
pem = pathlib.Path(certificate_path).read_text(encoding="ascii")
der = ssl.PEM_cert_to_DER_cert(pem)
certificate = {
    "subject": subject_map(decoded.get("subject", ())),
    "issuer": subject_map(decoded.get("issuer", ())),
    "serial_number": decoded.get("serialNumber"),
    "not_before": decoded.get("notBefore"),
    "not_after": decoded.get("notAfter"),
    "subject_alt_name": [
        {"type": item[0], "value": item[1]}
        for item in decoded.get("subjectAltName", ())
    ],
    "sha256_fingerprint": hashlib.sha256(der).hexdigest(),
}

user_names = []
userlist = pathlib.Path("/etc/pgbouncer/userlist.txt")
if userlist.exists():
    for raw in userlist.read_text(encoding="utf-8").splitlines():
        match = re.match(r'^\s*"([^"]+)"\s+', raw)
        if match:
            user_names.append(match.group(1))

listeners = []
for raw in subprocess.check_output(["ss", "-ltnH"], text=True).splitlines():
    fields = raw.split()
    if len(fields) < 4:
        continue
    match = re.search(r"(.+):([0-9]+)$", fields[3])
    if match and int(match.group(2)) in {
        5432, 5433, 5434, 5436, 5438, 6432, 8008
    }:
        listeners.append(
            {"address": match.group(1), "port": int(match.group(2))}
        )

print(json.dumps({
    "schema": "pg36-ch23-host-security-v1",
    "certificate": certificate,
    "files": {
        "server_certificate": metadata("/pg/cert/server.crt"),
        "server_private_key": metadata("/pg/cert/server.key"),
        "ca_certificate": metadata("/pg/cert/ca.crt"),
        "postgres_hba": metadata("/pg/data/pg_hba.conf"),
        "pgbouncer_ini": metadata("/etc/pgbouncer/pgbouncer.ini"),
        "pgbouncer_hba": metadata("/etc/pgbouncer/pgb_hba.conf"),
        "pgbouncer_userlist": metadata("/etc/pgbouncer/userlist.txt"),
        "postgres_log_directory": metadata("/pg/log/postgres"),
    },
    "pgbouncer": {
        "settings": parse_ini("/etc/pgbouncer/pgbouncer.ini"),
        "hba_rules": parse_hba("/etc/pgbouncer/pgb_hba.conf"),
        "declared_user_names": sorted(set(user_names)),
        "credential_values_redacted": True,
    },
    "listeners": sorted(listeners, key=lambda item: (item["port"], item["address"])),
}, sort_keys=True))
"""


def project_runtime_pgbouncer(
    user: str,
    host: str,
) -> dict[str, Any]:
    values = pgbouncer_config(user, host)
    numeric = {
        "listen_port",
        "max_client_conn",
        "default_pool_size",
        "reserve_pool_size",
        "reserve_pool_timeout",
        "query_wait_timeout",
        "max_prepared_statements",
        "server_reset_query_always",
    }
    text = {
        "pool_mode",
        "listen_addr",
        "server_reset_query",
        "client_tls_sslmode",
        "server_tls_sslmode",
        "auth_type",
    }
    result: dict[str, Any] = {}
    for key in sorted(numeric | text):
        if key not in values:
            result[key] = None
        elif key in numeric:
            result[key] = int(values[key])
        else:
            result[key] = values[key]
    return result


def capture_host(
    user: str,
    host: str,
) -> dict[str, Any]:
    postgres = remote_json_psql(
        user,
        host,
        "postgres",
        POSTGRES_SECURITY_SQL,
    )
    projection = remote_root_program_json(user, host, HOST_PROJECTION)
    if not isinstance(postgres, dict) or not isinstance(projection, dict):
        raise LabError(f"security projection on {host} is malformed")
    projection["pgbouncer"]["runtime_settings"] = (
        project_runtime_pgbouncer(user, host)
    )
    return {
        "address": host,
        "postgres": postgres,
        "host": projection,
    }


def capture_snapshot(
    requirements: dict[str, Any],
    user: str,
    phase: str,
) -> dict[str, Any]:
    target = requirements["target"]
    members = target["members"]
    observer = str(members["pg-test-3"])
    snapshot = {
        "schema": "pg36-ch23-security-snapshot-v1",
        "release": requirements["release"],
        "phase": phase,
        "captured_at": utc_now(milliseconds=True),
        "target": target["id"],
        "topology": patroni_list(user, observer),
        "members": {
            name: capture_host(user, str(members[name]))
            for name in sorted(members)
        },
    }
    ensure_no_secret_material(snapshot)
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", default="current")
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not re.fullmatch(r"[a-z0-9-]+", args.phase):
            raise LabError("phase name is not safe")
        requirements = read_json(args.requirements)
        value = capture_snapshot(
            requirements,
            args.ssh_user,
            args.phase,
        )
        write_json(args.output, value)
    except LabError as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    print(f"captured={args.output}")
    print("secret_material=excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
