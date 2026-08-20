default: dev

d:dev
dev:
	HUGO_MODULE_REPLACEMENTS='github.com/pgsty/oink -> $(HOME)/pgsty/oink' \
		hugo serve --renderToMemory

serve:
	hugo serve --environment production --minify --disableFastRender --disableLiveReload

b:build
build:
	hugo --gc --minify --cleanDestinationDir --panicOnWarning

check: check-book
	GOWORK=off go mod verify
	GOWORK=off hugo --gc --minify --cleanDestinationDir \
		--printPathWarnings --printI18nWarnings --panicOnWarning

check-local: check-book
	HUGO_MODULE_REPLACEMENTS='github.com/pgsty/oink -> $(HOME)/pgsty/oink' \
		hugo --gc --minify --cleanDestinationDir \
		--printPathWarnings --printI18nWarnings --panicOnWarning

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
