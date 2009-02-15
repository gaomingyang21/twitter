"""
USAGE:

 twitter [action] [options]

ACTIONS:
 follow         add the specified user to your follow list
 friends        get latest tweets from your friends (default action)
 leave			remove the specified user from your following list
 public         get latest public tweets
 replies        get latest replies
 set            set your twitter status

OPTIONS:

 -e --email <email>         your email to login to twitter
 -p --password <password>   your twitter password
 -r --refresh               run this command forever, polling every once
                            in a while (default: every 5 minutes)
 -R --refresh-rate <rate>   set the refresh rate (in seconds)
 -f --format <format>       specify the output format for status updates
 -c --config <filename>     read username and password from given config
                              file (default ~/.twitter)

FORMATS for the --format option

 default         one line per status
 verbose         multiple lines per status, more verbose status info
 urls            nothing but URLs. Dare you click them?
 
CONFIG FILES

 The config file should contain your email and password like so:

[twitter]
email: <username>
password: <password>
"""

import sys
import time
from getopt import getopt
from getpass import getpass
import re
import os.path
from ConfigParser import SafeConfigParser

from api import Twitter, TwitterError

options = {
    'email': None,
    'password': None,
    'action': 'friends',
    'refresh': False,
    'refresh_rate': 600,
    'format': 'default',
    'config_filename': os.environ.get('HOME', '') + os.sep + '.twitter',
    'extra_args': []
}

def parse_args(args, options):
    long_opts = ['email', 'password', 'help', 'format', 'refresh',
                 'refresh-rate', 'config']
    short_opts = "e:p:f:h?rR:c:"
    opts, extra_args = getopt(args, short_opts, long_opts)
    
    for opt, arg in opts:
        if opt in ('-e', '--email'):
            options['email'] = arg
        elif opt in ('-p', '--password'):
            options['password'] = arg
        elif opt in ('-f', '--format'):
            options['format'] = arg
        elif opt in ('-r', '--refresh'):
            options['refresh'] = True
        elif opt in ('-R', '--refresh-rate'):
            options['refresh_rate'] = int(arg)
        elif opt in ('-?', '-h', '--help'):
            print __doc__
            sys.exit(0)
        elif opt in ('-c', '--config'):
            options['config_filename'] = arg
    
    if extra_args:
        options['action'] = extra_args[0]
    options['extra_args'] = extra_args[1:]

class StatusFormatter(object):
    def __call__(self, status):
        return (u"%s %s" %(
            status['user']['screen_name'], status['text']))

class VerboseStatusFormatter(object):
    def __call__(self, status):
        return (u"-- %s (%s) on %s\n%s\n" %(
            status['user']['screen_name'],
            status['user']['location'],
            status['created_at'],
            status['text']))

class URLStatusFormatter(object):
    urlmatch = re.compile(r'https?://\S+')
    def __call__(self, status):
        urls = self.urlmatch.findall(status['text'])
        return u'\n'.join(urls) if urls else ""

class AdminFormatter(object):
	def __call__(self, action, user):
		return(u"%s: %s" %(
			"Following" if action == "follow" else "Leaving", user['name']))
			
class VerboseAdminFormatter(object):
	def __call__(self, action, user):
		return(u"-- %s: %s (%s): %s" % (
			"Following" if action == "follow" else "Leaving", 
			user['screen_name'], 
			user['name'],
			user['url']))
			
class URLAdminFormatter(object):
	def __call__(self, action, user):
		return("Admin actions do not support the URL formatter")

status_formatters = {
    'default': StatusFormatter,
    'verbose': VerboseStatusFormatter,
    'urls': URLStatusFormatter
}    

admin_formatters = {
	'default': AdminFormatter,
	'verbose': VerboseAdminFormatter,
	'urls': URLAdminFormatter
}
    
def get_status_formatter(options):
    sf = status_formatters.get(options['format'])
    if (not sf):
        raise TwitterError(
            "Unknown formatter '%s'" %(options['format']))
    return sf()

def get_admin_formatter(options):
	sf = admin_formatters.get(options['format'])
	if (not sf):
		raise TwitterError(
			"Unknown formatter '%s'" %(options['format']))
	return sf()
	
class Action(object):
    pass

class NoSuchAction(Action):
    def __call__(self, twitter, options):
        print >> sys.stderr, "No such action: ", options['action']
        sys.exit(1)

class StatusAction(Action):
    def __call__(self, twitter, options):
        statuses = self.getStatuses(twitter)
        sf = get_status_formatter(options)
        for status in statuses:
            statusStr = sf(status)
            if statusStr.strip():
                print statusStr.encode(sys.stdout.encoding, 'replace')

class AdminAction(Action):
	def __call__(self, twitter, options):
		if (not options['extra_args'][0]):
			raise TwitterError("You need to specify a User (Screen Name)")
		af = get_admin_formatter(options)
		user = self.getUser(twitter, options['extra_args'][0])
		if(user):
			print af(options['action'], user).encode(sys.stdout.encoding, 'replace')
        
class FriendsAction(StatusAction):
    def getStatuses(self, twitter):
        return reversed(twitter.statuses.friends_timeline())
 
class PublicAction(StatusAction):
    def getStatuses(self, twitter):
        return reversed(twitter.statuses.public_timeline())

class RepliesAction(StatusAction):
    def getStatuses(self, twitter):
        return reversed(twitter.statuses.replies())

class FollowAction(AdminAction):
	def getUser(self, twitter, user):
		# Twitter wants /notifications/follow/user.json?id=user
		return twitter.notifications.follow.__getattr__(user)(id=user)
		
class LeaveAction(AdminAction):
	def getUser(self, twitter, user):
		return twitter.notifications.leave.__getattr__(user)(id=user)

class SetStatusAction(Action):
    def __call__(self, twitter, options):
        statusTxt = (u" ".join(options['extra_args']) 
                     if options['extra_args'] 
                     else unicode(raw_input("message: ")))
        status = (statusTxt.encode('utf8', 'replace'))
        twitter.statuses.update(status=status)

actions = {
	'follow': FollowAction,
    'friends': FriendsAction,
    'leave': LeaveAction,
    'public': PublicAction,
    'replies': RepliesAction,
    'set': SetStatusAction,
}

def loadConfig(filename):
    email = None
    password = None
    if os.path.exists(filename):
        cp = SafeConfigParser()
        cp.read([filename])
        email = cp.get('twitter', 'email', None)
        password = cp.get('twitter', 'password', None)
    return email, password

def main():
    return main_with_args(sys.argv[1:])
    
def main_with_args(args):
    parse_args(args, options)

    email, password = loadConfig(options['config_filename'])
    if not options['email']: options['email'] = email
    if not options['password']: options['password'] = password
   
    #Maybe check for AdminAction here, but whatever you do, don't write TODO
    if options['refresh'] and options['action'] == 'set':
        print >> sys.stderr, "You can't repeatedly set your status, silly"
        print >> sys.stderr, "Use 'twitter -h' for help."
        sys.exit(1)
    if options['email'] and not options['password']:
        options['password'] = getpass("Twitter password: ")
    twitter = Twitter(options['email'], options['password'])
    action = actions.get(options['action'], NoSuchAction)()
    try:
        doAction = lambda : action(twitter, options)
	        
        if (options['refresh'] and isinstance(action, StatusAction)):
           while True:
              doAction()
              time.sleep(options['refresh_rate'])
        else:
           doAction()
			
    except TwitterError, e:
        print >> sys.stderr, e.args[0]
        print >> sys.stderr, "Use 'twitter -h' for help."
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    
