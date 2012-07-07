#! /usr/bin/env python
#
# twistory is a tool to retrieve your twitter history.  That is, it will
# fetch all the messages you tweeted and print them to STDOUT.  twistory
# will prefix the message with the message-ID and suffix it with the
# timestamp.
#
# Copyright (c) 2011,2012, Jan Schaumann. All rights reserved.
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

    def __init__(self):
        """Construct a Twistory object with default values."""

        self.__opts = {
                    "after"    : -1,
                    "before"   : -1,
                    "lineify"  : False,
                    "retweets" : False,
                    "user"     : ""
                 }


    class Usage(Exception):
        """A simple exception that provides a usage statement and a return code."""

        def __init__(self, rval):
            self.err = rval
            self.msg = 'Usage: %s [-hr] [-[ab] id] -u user\n' % os.path.basename(sys.argv[0])
            self.msg += '\t-a after   get history since this message\n'
            self.msg += '\t-b before  get history prior to this message\n'
            self.msg += '\t-h         print this message and exit\n'
            self.msg += '\t-r         print messages that were retweeted\n'
            self.msg += '\t-u user    get history of this user\n'


    def displayTimeline(self):
        """Print the requested timeline."""

        while True:
                before = self.getOpt("before")
                after = self.getOpt("after")
                user = self.getOpt("user")
                apicall = tweepy.api.user_timeline
                if self.getOpt("retweets"):
                    apicall = tweepy.api.retweeted_by_user
                try:
                    for status in tweepy.Cursor(apicall, id=user).items():
                        if (before == -1):
                            # Ugh. Kludge.  If '-b' was not given, we'd
                            # like to default to infinity, but that isn't
                            # working so well, so let's grab the latest
                            # message of the user in question.  Add one to
                            # also include that message itself in the
                            # results.
                            before = status.id + 1

                        if (status.id < after):
                            # Just save us a few pages.  We could of
                            # course just iterate over all messages, but
                            # that doesn't do us any good since the API
                            # does return results sorted already.
                            break

                        if ((before > status.id) and (status.id > after)):
                            msg = status.text.encode("UTF-8")
                            if self.getOpt("lineify"):
                                msg = msg.replace("\n", "\\n")
                            print "%s %s (%s)" % (status.id, msg, status.created_at)
                except tweepy.error.TweepError, e:
                    self.handleTweepError(e, "Unable to get messages for %s" % user)

                break


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
            rate_limit = tweepy.api.rate_limit_status()
        except tweepy.error.TweepError, e:
            # Hey now, look at that, we can failwahle on getting the api
            # status. Neat, huh? Let's pretend that didn't happen and move
            # on, why not.
            return

        if tweeperr and tweeperr.response and tweeperr.response.status:
            if tweeperr.response.status == TWITTER_RESPONSE_STATUS["FailWhale"]:
                errmsg = "Twitter #FailWhale'd on me on %s." % time.asctime()
            elif tweeperr.response.status == TWITTER_RESPONSE_STATUS["Broken"]:
                errmsg = "Twitter is busted again: %s" % time.asctime()
            elif tweeperr.response.status == TWITTER_RESPONSE_STATUS["RateLimited"] or \
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

        sys.stderr.write(info + "\n" + errmsg)

        if diff:
            sys.stderr.write("Sleeping for %d seconds...\n" % diff)
            time.sleep(diff)



    def parseOptions(self, inargs):
        """Parse given command-line options and set appropriate attributes.

        Arguments:
            inargs -- arguments to parse

        Raises:
            Usage -- if '-h' or invalid command-line args are given
        """

        try:
            opts, args = getopt.getopt(inargs, "a:b:hlru:")
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
            except ValueError, e:
                sys.stderr.write("Invalid argument for option %s: %s\n" % (o, e))
                sys.exit(EXIT_ERROR)

        if not self.getOpt("user") or args:
            raise self.Usage(EXIT_ERROR)


    def setOpt(self, opt, val):
        """Set the given option to the provided value."""

        self.__opts[opt] = val


###
### "Main"
###

if __name__ == "__main__":
    try:
        reload(sys)
        sys.setdefaultencoding("UTF-8")

        twistory = Twistory()
        try:
            twistory.parseOptions(sys.argv[1:])
            twistory.displayTimeline()

        except twistory.Usage, u:
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
