# A simple Makefile to (un)install twistory.

PREFIX=/usr/local
PYTHON?=python

all:
	@echo "Available targets:"
	@echo " install"
	@echo " uninstall"

check:
	@if ! echo "import tweepy" | ${PYTHON} 2>/dev/null ; then \
		echo "Please install https://github.com/tweepy/tweepy" >&2 ; \
		exit 1;						\
	fi


install: check
	mkdir -p ${PREFIX}/bin
	mkdir -p ${PREFIX}/share/man/man1
	install -c -m 755 src/twistory.py ${PREFIX}/bin/twistory
	install -c -m 444 doc/twistory.1 ${PREFIX}/share/man/man1/twistory.1

uninstall:
	rm -f ${PREFIX}/bin/twistory ${PREFIX}/share/man/man1/twistory.1
