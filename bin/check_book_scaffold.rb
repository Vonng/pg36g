#!/usr/bin/env ruby
# frozen_string_literal: true

require "pathname"
require "tmpdir"
require "uri"
require "yaml"
require "open3"

ROOT = Pathname.new(__dir__).parent.expand_path
DOCS = ROOT.join("docs")
CHAPTERS_DATA = ROOT.join("data/chapters.yaml")
ARCHIVE = ROOT.join("archive/2026-07-29-pre-scaffold/docs")
NESTED_SCAFFOLD_ARCHIVE = ROOT.join("archive/2026-07-29-nested-volume-scaffold/docs")

def fail_check(message)
  warn "FAIL: #{message}"
  exit 1
end

def front_matter(path)
  parts = path.read.split(/^---\s*$\n?/, 3)
  fail_check("missing front matter in #{path}") unless parts.length == 3
  YAML.safe_load(parts[1], aliases: false)
end

def source_url(path)
  relative = path.relative_path_from(DOCS).to_s
  if relative == "_index.md"
    "/"
  elsif relative.end_with?("/_index.md")
    "/#{relative.delete_suffix('/_index.md')}/"
  else
    "/#{relative.delete_suffix('.md')}/"
  end
end

def resolve_link(current_url, link)
  path, fragment = link.split("#", 2)
  return [current_url, fragment] if path.nil? || path.empty?

  base = URI("https://book.invalid#{current_url}")
  resolved = URI.join(base.to_s, path)
  [resolved.path, fragment]
rescue URI::InvalidURIError
  [nil, nil]
end

def built_target(build_dir, url_path)
  clean = url_path.sub(%r{\A/}, "")
  return build_dir.join("index.html") if clean.empty?

  candidate = build_dir.join(clean)
  return candidate if candidate.file?
  return candidate.join("index.html") if candidate.directory?

  build_dir.join(clean, "index.html")
end

fail_check("missing #{CHAPTERS_DATA}") unless CHAPTERS_DATA.file?
fail_check("missing archive #{ARCHIVE}") unless ARCHIVE.directory?
archive_file_count = Dir.glob(ARCHIVE.join("**/*").to_s, File::FNM_DOTMATCH).count do |path|
  File.file?(path) && File.basename(path) != ".DS_Store"
end
fail_check("archive source file count changed: #{archive_file_count}") unless archive_file_count == 76
fail_check("missing nested scaffold archive #{NESTED_SCAFFOLD_ARCHIVE}") unless NESTED_SCAFFOLD_ARCHIVE.directory?
nested_archive_file_count = Dir.glob(NESTED_SCAFFOLD_ARCHIVE.join("**/*").to_s, File::FNM_DOTMATCH).count { |path| File.file?(path) }
fail_check("nested scaffold archive file count changed: #{nested_archive_file_count}") unless nested_archive_file_count == 302
fail_check("missing scaffold sentinel") unless DOCS.join(".scaffold-generated").read.strip == "generated-by=bin/scaffold_book.rb"

chapters = YAML.safe_load(CHAPTERS_DATA.read, aliases: false)
fail_check("expected 36 chapters, got #{chapters.length}") unless chapters.length == 36
fail_check("chapter sequence mismatch") unless chapters.map { |chapter| chapter["number"] } == (1..36).to_a
fail_check("chapter slugs are not unique") unless chapters.map { |chapter| chapter["slug"] }.uniq.length == 36

section_count = chapters.sum { |chapter| chapter["sections"].length }
item_count = chapters.sum { |chapter| chapter["sections"].sum { |section| section["items"].length } }
fail_check("expected 242 formal section pages, got #{section_count}") unless section_count == 242
fail_check("expected 772 formal item summaries, got #{item_count}") unless item_count == 772

chapters.each do |chapter|
  chapter_dir = DOCS.join(chapter["slug"])
  fail_check("missing chapter index #{chapter['id']}") unless chapter_dir.join("_index.md").file?
  fail_check("#{chapter['id']} directory still exposes capability attribution") if chapter_dir.join("_index.md").read.include?("能力归属")
  fail_check("#{chapter['id']} section count outside 5..8") unless (5..8).cover?(chapter["sections"].length)

  chapter["sections"].each do |section|
    page = chapter_dir.join("#{section['slug']}.md")
    fail_check("missing section page #{section['id']}") unless page.file?
    content = page.read
    fail_check("#{section['id']} missing scaffold status") unless content.include?("book_status: scaffold")
    fail_check("#{section['id']} still exposes capability attribution") if content.include?("**能力归属**")
    fail_check("#{section['id']} item count outside 2..4") unless (2..4).cover?(section["items"].length)

    section["items"].each do |item|
      heading = "## #{item['number']} #{item['title']} {##{item['id']}}"
      fail_check("#{section['id']} missing heading #{item['number']}") unless content.include?(heading)
      pattern = /^## #{Regexp.escape(item['number'].to_s)} .+? \{##{Regexp.escape(item['id'])}\}\n\n([^\n]+)$/m
      match = content.match(pattern)
      fail_check("#{item['id']} missing one-paragraph summary") unless match
      summary = match[1].strip
      fail_check("#{item['id']} summary is too short") if summary.length < 70
      fail_check("#{item['id']} summary contains placeholder") if summary.match?(/TODO|TBD|待补|占位/)
    end
  end
end

chapter_zero_pages = DOCS.glob("ch00/[0-9][0-9].md")
fail_check("expected 3 chapter-zero section pages") unless chapter_zero_pages.length == 3

all_section_pages = chapters.flat_map do |chapter|
  DOCS.glob("#{chapter['slug']}/[0-9][0-9].md")
end
fail_check("filesystem section count mismatch") unless all_section_pages.length == 242

all_item_headings = all_section_pages.sum do |page|
  page.read.scan(/^## \d+\.\d+\.\d+ .+ \{#item-\d+-\d+-\d+\}$/).length
end
fail_check("filesystem item heading count mismatch: #{all_item_headings}") unless all_item_headings == 772

required_pages = %w[
  _index.md
  preface.md
  toc.md
  upper-volume.md
  lower-volume.md
  guide/_index.md
  indexes/_index.md
  indexes/roles.md
  indexes/tasks.md
  indexes/capabilities.md
  indexes/incidents.md
  indexes/partition.md
  appendices/_index.md
]
required_pages.each do |relative|
  fail_check("missing index page docs/#{relative}") unless DOCS.join(relative).file?
end
DOCS.glob("**/*.md").each do |page|
  metadata = front_matter(page)
  navigation_label = [metadata["title"], metadata["linkTitle"]].compact.join(" ")
  fail_check("navigation label still exposes capability attribution in #{page.relative_path_from(ROOT)}") if navigation_label.include?("能力归属")
end
fail_check("volume-1 must not be a source navigation directory") if DOCS.join("volume-1").exist?
fail_check("volume-2 must not be a source navigation directory") if DOCS.join("volume-2").exist?
fail_check("obsolete docs/volume-1.md still exists") if DOCS.join("volume-1.md").exist?
fail_check("obsolete docs/volume-2.md still exists") if DOCS.join("volume-2.md").exist?
fail_check("full table of contents still exposes capability attribution") if DOCS.join("toc.md").read.match?(/能力归属|`(?:PG|平台|Pigsty)`/)
fail_check("upper-volume index still exposes capability attribution") if DOCS.join("upper-volume.md").read.include?("能力归属")
fail_check("lower-volume index still exposes capability attribution") if DOCS.join("lower-volume.md").read.include?("能力归属")

upper_weight = front_matter(DOCS.join("upper-volume.md")).fetch("weight")
chapter_1_weight = front_matter(DOCS.join(chapters[0]["slug"], "_index.md")).fetch("weight")
chapter_18_weight = front_matter(DOCS.join(chapters[17]["slug"], "_index.md")).fetch("weight")
lower_weight = front_matter(DOCS.join("lower-volume.md")).fetch("weight")
chapter_19_weight = front_matter(DOCS.join(chapters[18]["slug"], "_index.md")).fetch("weight")
fail_check("upper-volume page is not ordered immediately before ch01") unless upper_weight < chapter_1_weight
fail_check("lower-volume page is not ordered between ch18 and ch19") unless chapter_18_weight < lower_weight && lower_weight < chapter_19_weight

Dir.mktmpdir("pg36g-book-check") do |temporary|
  build_dir = Pathname.new(temporary)
  stdout, stderr, status = Open3.capture3(
    "hugo",
    "--destination",
    build_dir.to_s,
    chdir: ROOT.to_s
  )
  unless status.success?
    warn stdout
    warn stderr
    fail_check("Hugo build failed")
  end

  chapters.each do |chapter|
    alias_page = build_dir.join(format("ch%02d/index.html", chapter["number"]))
    fail_check("missing alias /ch#{format('%02d', chapter['number'])}/") unless alias_page.file?
    expected_target = "/#{chapter['slug']}/"
    fail_check("alias /ch#{format('%02d', chapter['number'])}/ points to the wrong target") unless alias_page.read.include?(expected_target)

    nested_alias = build_dir.join(chapter["volume"], chapter["slug"], "index.html")
    fail_check("missing former nested chapter alias for #{chapter['id']}") unless nested_alias.file?
    fail_check("former nested chapter alias for #{chapter['id']} points to the wrong target") unless nested_alias.read.include?(expected_target)

    chapter["sections"].each do |section|
      nested_section_alias = build_dir.join(
        chapter["volume"],
        chapter["slug"],
        section["slug"],
        "index.html"
      )
      expected_section_target = "#{expected_target}#{section['slug']}/"
      fail_check("missing former nested section alias for #{section['id']}") unless nested_section_alias.file?
      fail_check("former nested section alias for #{section['id']} points to the wrong target") unless nested_section_alias.read.include?(expected_section_target)
    end
  end

  %w[upper-volume lower-volume].each do |volume_slug|
    volume_page = build_dir.join(volume_slug, "index.html")
    fail_check("missing rendered #{volume_slug} overview") unless volume_page.file?
    fail_check("#{volume_slug} overview rendered as a redirect") if volume_page.read.include?("http-equiv=\"refresh\"")
  end

  { "volume-1" => "/upper-volume/", "volume-2" => "/lower-volume/" }.each do |legacy_path, target|
    alias_page = build_dir.join(legacy_path, "index.html")
    fail_check("missing legacy volume alias /#{legacy_path}/") unless alias_page.file?
    fail_check("legacy volume alias /#{legacy_path}/ points to the wrong target") unless alias_page.read.include?(target)
  end

  markdown_files = DOCS.glob("**/*.md")
  checked_links = 0
  markdown_files.each do |source|
    current_url = source_url(source)
    source.read.scan(/\[[^\]]*\]\(([^)\s]+)\)/).flatten.each do |link|
      next if link.match?(%r{\A(?:https?:|mailto:|tel:)})

      url_path, fragment = resolve_link(current_url, link)
      fail_check("invalid link #{link} in #{source}") unless url_path
      target = built_target(build_dir, url_path)
      fail_check("broken link #{link} in #{source.relative_path_from(ROOT)}") unless target.file?
      if fragment && !fragment.empty? && target.extname == ".html"
        html = target.read
        fail_check("missing anchor ##{fragment} for #{link}") unless html.include?("id=\"#{fragment}\"")
      end
      checked_links += 1
    end
  end

  sample = build_dir.join("deployment-baseline/02/index.html")
  fail_check("missing rendered sample section") unless sample.file?
  fail_check("sample item anchor not rendered") unless sample.read.include?('id="item-19-2-1"')

  puts "PASS: 36 chapters, 242 formal section pages, 772 formal item summaries"
  puts "PASS: 76 archived source files preserved (Finder metadata excluded)"
  puts "PASS: 302 nested-volume scaffold files preserved"
  puts "PASS: Hugo built successfully; #{checked_links} internal Markdown links resolved"
end
