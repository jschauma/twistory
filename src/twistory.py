#! /usr/bin/env python3.10
#
# twistory is a tool to retrieve your twitter history.  That is, it will
# fetch all the messages you tweeted and print them to STDOUT.  twistory
# will prefix the message with the message-ID and suffix it with the
# timestamp.
#
# Copyright (c) 2011,2012,2013, Jan Schaumann. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#
#    2. Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL <COPYRIGHT HOLDER> OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Originally written by Jan Schaumann <jschauma@netmeister.org> in May 2011.

import getopt
import http.client
import os
import re
import sys
import time
import tweepy

EXIT_ERROR = 1
EXIT_SUCCESS = 0

# http://apiwiki.twitter.com/w/page/22554652/HTTP-Response-Codes-and-Errors
TWITTER_RESPONSE_STATUS = {
        "OK" : 200,
        "NotModified" : 304,
        "RateLimited" : 400,
        "Unauthorized" : 401,
        "Forbidden" : 403,
        "NotFound" : 404,
        "NotAcceptable" : 406,
        "SearchRateLimited" : 420,
        "Broken" : 500,
        "Down" : 502,
        "FailWhale" : 503
    }


###
### Classes
###

class Twistory(object):
    """A simple twitter history display object."""

    EXIT_ERROR = 1
    EXIT_SUCCESS = 0

    def __init__(self):
        """Construct a Twistory object with default values."""

        self.__opts = {
                    "after"    : -1,
                    "before"   : -1,
                    "cfg_file" : os.path.expanduser("~/.twistory"),
                    "lineify"  : False,
                    "retweets" : False,
                    "user"     : ""
                 }
        self.auth = None
        self.api = None
        self.api_credentials = {}
        self.users = {}
        self.verbosity = 0


    class Usage(Exception):
        """A simple exception that provides a usage statement and a return code."""

        def __init__(self, rval):
            self.err = rval
            self.msg = 'Usage: %s [-hrv] [-[ab] id] -u user\n' % os.path.basename(sys.argv[0])
            self.msg += '\t-a after   get history since this message\n'
            self.msg += '\t-b before  get history prior to this message\n'
            self.msg += '\t-h         print this message and exit\n'
            self.msg += '\t-r         print messages that were retweeted\n'
            self.msg += '\t-u user    get history of this user\n'
            self.msg += '\t-v         increase verbosity\n'


    def displayTimeline(self):
        """Print the requested timeline."""

        self.verbose("Fetching tweets...")
        count = 1
        lastid = None

        tco_re = re.compile("https?://t.co/(?P<code>[0-9a-z]+)", re.I)
        before = self.getOpt("before")
        after = self.getOpt("after")
        user = self.getOpt("user")
        apicall = self.api.user_timeline
        loop = True
        if self.getOpt("retweets"):
            apicall = self.api.retweeted_by
        while loop:
            try:
                pageitems = apicall(screen_name=user, max_id=lastid, count=200)
                print("%s" % user)
                if not pageitems:
                    break
                for status in pageitems:
                    lastid = status.id - 1
                    self.verbose("Iterating (%d)..." % count, 2)
                    if (before == -1):
                        # Ugh. Kludge.  If '-b' was not given, we'd
                        # like to default to infinity, but that isn't
                        # working so well, so let's grab the latest
                        # message of the user in question.  Add one to
                        # also include that message itself in the
                        # results.
                        before = status.id + 1

                    if (status.id < after):
                        self.verbose("Tweet earlier than threshold, breaking out.", 2)
                        # Just save us a few pages.  We could of
                        # course just iterate over all messages, but
                        # that doesn't do us any good since the API
                        # does return results sorted already.
                        loop = False
                        break

                    count = count + 1
                    self.verbose("Before: %d; Status: %d; After: %d, lastid: %d" % (before, status.id, after, lastid), 4)
                    if ((before > status.id) and (status.id > after)):
                        msg = status.text.encode("UTF-8")
                        for m in tco_re.finditer(msg):
                            code = m.group('code')
                            self.verbose("Unwrapping %s..." % code, 3)
                            h = http.client.HTTPConnection("t.co")
                            h.request("GET", "/" + code)
                            r = h.getresponse()
                            link = r.getheader("Location")
                            if link:
                                tco = re.compile("https?://t.co/" + code)
                                msg = re.sub(tco, link, msg)
                        if self.getOpt("lineify"):
                            msg = msg.replace("\n", "\\n")
                        print("%s %s (%s)" % (status.id, msg, status.created_at))
            except Exception as e:
                self.verbose(e)
            except http.client.IncompleteRead as e:
                self.verbose("Incomplete read, trying again in 5 seconds.")
                time.sleep(5)
            except tweepy.error.TweepError as e:
                if not self.handleTweepError(e, "Unable to get messages for %s" % user):
                    break

            # We reset 'lastid' on each loop; we set it on each item
            # found. If it's None, then we have no more items to fetch and
            # should terminate the loop.
            if not lastid:
                break


    def getAccessInfo(self, user):
        """Initialize OAuth Access Info (if not found in the configuration file)."""

        self.auth = tweepy.OAuthHandler(self.api_credentials['key'], self.api_credentials['secret'])
        if user in self.users:
            return

        auth_url = self.auth.get_authorization_url(True)
        print("Access credentials for %s not found in %s." % (user, self.getOpt("cfg_file")))
        print("Please log in on twitter.com as %s and then go to: " % user)
        print("  " + auth_url)
        verifier = raw_input("Enter PIN: ").strip()
        self.auth.get_access_token(verifier)

        self.users[user] = {
            "key" : self.auth.access_token.key,
            "secret" : self.auth.access_token.secret
        }

        cfile = self.getOpt("cfg_file")
        try:
            f = file(cfile, "a")
            f.write("%s_key = %s\n" % (user, self.auth.access_token.key))
            f.write("%s_secret = %s\n" % (user, self.auth.access_token.secret))
            f.close()
        except IOError as e:
            sys.stderr.write("Unable to write to config file '%s': %s\n" % \
                (cfile, e.strerror))
            raise



    def getOpt(self, opt):
        """Retrieve the given configuration option.

        Returns:
            The value for the given option if it exists, None otherwise.
        """

        try:
            r = self.__opts[opt]
        except ValueError:
            r = None

        return r

    def handleTweepError(self, tweeperr, info):
        """Try to handle a Tweepy Error by bitching about it."""

        diff = 0
        errmsg = ""

        try:
            rate_limit = self.api.rate_limit_status()
        except tweepy.error.TweepError as e:
            # Hey now, look at that, we can failwahle on getting the api
            # status. Neat, huh? Let's pretend that didn't happen and move
            # on, why not.
            return

        if hasattr(tweeperr, 'response'):
            response = tweeperr.response
            if hasattr(response, 'status'):
                status = response.status
                if status == TWITTER_RESPONSE_STATUS["FailWhale"]:
                    errmsg = "Twitter #FailWhale'd on me on %s." % time.asctime()
                elif status == TWITTER_RESPONSE_STATUS["Broken"]:
                    errmsg = "Twitter is busted again: %s" % time.asctime()
                elif status == TWITTER_RESPONSE_STATUS["RateLimited"] or \
                    tweeperr.response.status == TWITTER_RESPONSE_STATUS["SearchRateLimited"]:
                    errmsg = "Rate limited until %s." % rate_limit["reset_time"]
                    diff = rate_limit["reset_time_in_seconds"] - time.time()
                    if rate_limit["remaining_hits"] > 0:
                        # False alarm?  We occasionally seem to hit a race
                        # condition where one call falls directly onto the
                        # reset time, so we appear to be throttled for 59:59
                        # minutes, but actually aren't.  Let's pretend that
                        # didn't happen.
                        return
                else:
                    errmsg = "On %s Twitter told me:\n'%s'" % (time.asctime(), tweeperr)
        else:
            errmsg = tweeperr.reason

        sys.stderr.write(info + "\n" + errmsg + "\n")

        if diff:
            diff = diff + 2
            sys.stderr.write("Sleeping for %d seconds...\n" % diff)
            time.sleep(diff)
            return True

        return False


    def parseConfig(self, cfile):
        """Parse the configuration file and set appropriate variables.

        This function may throw an exception if it can't read or parse the
        configuration file (for any reason).

        Arguments:
            cfile -- the configuration file to parse

        Aborts:
            if we can't access the config file
        """

        try:
            f = open(cfile, "r")
        except IOError as e:
            sys.stderr.write("Unable to open config file '%s': %s\n" % \
                (cfile, e.strerror))
            sys.exit(self.EXIT_ERROR)

        key_pattern = re.compile('^(?P<username>[^#]+)_key\s*=\s*(?P<key>.+)')
        secret_pattern = re.compile('^(?P<username>[^#]+)_secret\s*=\s*(?P<secret>.+)')
        for line in f.readlines():
            line = line.strip()
            key_match = key_pattern.match(line)
            if key_match:
                user = key_match.group('username')
                if user == "<api>":
                    self.api_credentials['key'] = key_match.group('key')
                else:
                    if user in self.users:
                        self.users[user]['key'] = key_match.group('key')
                    else:
                        self.users[user] = {
                            "key" : key_match.group('key')
                        }

            secret_match = secret_pattern.match(line)
            if secret_match:
                user = secret_match.group('username')
                if user == "<api>":
                    self.api_credentials['secret'] = secret_match.group('secret')
                else:
                    if user in self.users:
                        self.users[user]['secret'] = secret_match.group('secret')
                    else:
                        self.users[user] = {
                            "secret" : secret_match.group('secret')
                        }
        f.close()


    def parseOptions(self, inargs):
        """Parse given command-line options and set appropriate attributes.

        Arguments:
            inargs -- arguments to parse

        Raises:
            Usage -- if '-h' or invalid command-line args are given
        """

        try:
            opts, args = getopt.getopt(inargs, "a:b:hlru:v")
        except getopt.GetoptError:
            raise self.Usage(EXIT_ERROR)

        for o, a in opts:
            try:
                if o in ("-a"):
                    self.setOpt("after", int(a))
                if o in ("-b"):
                    self.setOpt("before", int(a))
                if o in ("-h"):
                    raise self.Usage(EXIT_SUCCESS)
                if o in ("-l"):
                    self.setOpt("lineify", True)
                if o in ("-r"):
                    self.setOpt("retweets", True)
                if o in ("-u"):
                    self.setOpt("user", a)
                if o in ("-v"):
                    self.verbosity = self.verbosity + 1
            except ValueError as e:
                sys.stderr.write("Invalid argument for option %s: %s\n" % (o, e))
                sys.exit(EXIT_ERROR)

        if not self.getOpt("user") or args:
            raise self.Usage(EXIT_ERROR)


    def setOpt(self, opt, val):
        """Set the given option to the provided value."""

        self.__opts[opt] = val


    def setupApi(self, user):
        """Create the object's api"""

        key = self.users[user]["key"]
        secret = self.users[user]["secret"]
        self.auth.set_access_token(key, secret)

        self.api = tweepy.API(self.auth)


    def verbose(self, msg, level=1):
        """Print given message to STDERR if the object's verbosity is >=
           the given level"""

        if (self.verbosity >= level):
            sys.stderr.write("%s> %s\n" % ('=' * level, msg))


    def verifyConfig(self):
        """Verify that we have api credentials."""

        if (not ("key" in self.api_credentials and "secret" in self.api_credentials)):
            sys.stderr.write("No API credentials found.  Please do the 'register-this-app' dance.\n")
            sys.exit(self.EXIT_ERROR)



###
### "Main"
###

if __name__ == "__main__":
    try:
        twistory = Twistory()
        try:
            twistory.parseOptions(sys.argv[1:])
            twistory.parseConfig(twistory.getOpt("cfg_file"))
            twistory.verifyConfig()

            user = twistory.getOpt("user")
            twistory.getAccessInfo(user)
            twistory.setupApi(user)

            twistory.displayTimeline()

        except twistory.Usage as u:
            if (u.err == EXIT_ERROR):
                out = sys.stderr
            else:
                out = sys.stdout
            out.write(u.msg)
            sys.exit(u.err)
	        # NOTREACHED

    except KeyboardInterrupt:
        # catch ^C, so we don't get a "confusing" python trace
        sys.exit(EXIT_ERROR)
