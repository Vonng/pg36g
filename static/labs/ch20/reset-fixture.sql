\set ON_ERROR_STOP on

DO $guard$
BEGIN
    IF current_database() <> 'test' THEN
        RAISE EXCEPTION
            'chapter 20 fixture may be removed only from database test';
    END IF;
END
$guard$;

DROP SCHEMA pg36_ch20 CASCADE;
