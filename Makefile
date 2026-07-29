default: dev

d:dev
dev:
	hugo serve --disableFastRender --renderToMemory

b:build
build:
	hugo --gc --minify --cleanDestinationDir --panicOnWarning

scaffold:
	ruby bin/scaffold_book.rb

scaffold-refresh:
	ruby bin/scaffold_book.rb --refresh

check-book:
	ruby bin/check_book_scaffold.rb

.PHONY: default d dev b build scaffold scaffold-refresh check-book

# generate zh-tw version
translate:
	bin/zh-tw.py

epub:
	bin/epub

.PHONY: default doc translate
