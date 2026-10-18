HUGO ?= hugo
OINK_LOCAL ?= $(HOME)/pgsty/oink
PORT ?= 1313

# Keep local development independent of module workspaces and vendored pins.
export GOWORK := off
export HUGO_MODULE_WORKSPACE := off
PINNED_HUGO = env -u HUGO_MODULE_REPLACEMENTS $(HUGO)
LOCAL_HUGO = HUGO_MODULE_REPLACEMENTS="github.com/pgsty/oink -> $(abspath $(OINK_LOCAL))" $(HUGO) --ignoreVendorPaths=github.com/pgsty/oink

default: dev

d:dev
dev: theme-local
	$(LOCAL_HUGO) serve --renderToMemory --bind 127.0.0.1 --port "$(PORT)" --noBuildLock

serve:
	$(PINNED_HUGO) serve --environment production --minify --disableFastRender --disableLiveReload

b:build
build:
	$(PINNED_HUGO) --gc --minify --cleanDestinationDir

check: check-book
	GOWORK=off go mod verify
	$(PINNED_HUGO) --gc --minify --cleanDestinationDir \
		--printPathWarnings --printI18nWarnings

check-local: theme-local check-book
	$(LOCAL_HUGO) --gc --minify --cleanDestinationDir \
		--printPathWarnings --printI18nWarnings

scaffold:
	ruby bin/scaffold_book.rb

scaffold-refresh:
	ruby bin/scaffold_book.rb --refresh

check-book:
	ruby bin/check_book_scaffold.rb

.PHONY: default d dev serve b build check check-local scaffold scaffold-refresh check-book

# generate zh-tw version
translate:
	bin/zh-tw.py

epub:
	bin/epub

.PHONY: default doc translate

# Fail explicitly if a local theme was requested but is unavailable.
theme-local:
	@test -f "$(OINK_LOCAL)/hugo.yaml" || { echo "Set OINK_LOCAL to an OINK checkout (default: ~/pgsty/oink)." >&2; exit 1; }

.PHONY: theme-local
