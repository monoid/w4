from twisted.python.components import registerAdapter
from twisted.python import log
from twisted.web import static, server
from twisted.web.resource import Resource
from twisted.words.protocols.jabber.xmpp_stringprep import resourceprep
from zope.interface import Interface, Attribute, implements

from collections import deque

import json
import re
import time
import weakref

VALID_NICK = re.compile(r'^\S.*\S$', re.UNICODE)

SESSION_TIMEOUT = 300     # Ten minutes
POLL_TIMEOUT = 120-0.2    # Almost two minutes
GC_PERIOD = 10            # Half minute

HISTORY_SIZE = 10


# TODO: group should have an ACL.  Even public group has an ACL where
# its owners are listed.
class Group:
    name = None
    public = True
    channels = None
    history = None
    subject = None

    # Class attribute
    groups = {}

    def __init__(self, name):
        self.name = name
        self.channels = weakref.WeakValueDictionary()
        self.history = History()

        Group.groups[name] = self

    def join(self, chan, nickname):
        if self.public:
            hist = list(self.history)
            if self.subject:
                hist += [{'cmd': 'subject', 'message': self.subject}]
            chan.sendMessages(hist)

            # Leave group if the channel have been logged before with
            # different names
            if self.name in chan.groups:
                if chan.groups[self.name] != nickname:
                    self.leave(chan)
                else:
                    # Just return, as this is returning user
                    return True

            self.channels[nickname] = chan
            chan.groups[self.name] = nickname

            self.broadcast({
                'cmd': 'join',
                'user': nickname
            })
            return True
        else:
            # TODO: check ACL
            chan.error('Access denied', self)
            return False

    def leave(self, chan):
        nickname = chan.groups[self.name]
        if nickname in self.channels:
            self.broadcast({
                'cmd': 'leave',
                'user': nickname
            })
            del self.channels[nickname]
            del chan.groups[self.name]
            return True
        else:
            # TODO exception
            return False

    def broadcast(self, message):
        message['ts'] = int(1000*time.time())
        self.history.message(message)
        for chan in self.channels.values():
            chan.sendMessages([message])


######################################################################

class IUser(Interface):
    # TODO: id
    name = Attribute("User name")


class User():
    implements(IUser)

    # Class attribute
    users = {}

    def __init__(self, _):
        self.name = None

registerAdapter(User, server.Session, IUser)


class IChannel(Interface):
    messages = Attribute("")
    poll = Attribute("")
    user = Attribute("")
    groups = Attribute("Dict of channel's group by name.")
    ts = Attribute("Poll's timestamp")
    to = Attribute("Poll's timeout")


class Channel:
    implements(IChannel)
    messages = None
    poll = None
    user = None
    # Dict groupname -> nickname
    groups = None
    ts = None
    to = POLL_TIMEOUT

    # Class attribute
    channels = {}

    def __init__(self, session):
        self.messages = [{'cmd': 'ping'}]  # Force request completion
                                           # to set session cookie.
        self.groups = {}
        Channel.channels[session.uid] = self
        self.uid = session.uid

        self.ts = time.time()

        def onExpire():
            self.close(session)

        session.notifyOnExpire(onExpire)
        session.sessionTimeout = SESSION_TIMEOUT

    def setPoll(self, poll):
        if self.poll:
            poll.setResponseCode(403) # TODO
            poll.setHeader('Content-type', 'application/json')
            json.dump([{
                'cmd': 'error',
                'type': 'duplicate-pall',
                'msg': "It seems you opened chat in multiple windows..."
            }], poll)
            poll.finish()
            return

        self.poll = poll
        self.ts = time.time()
        notify = self.poll.notifyFinish()
        notify.addCallback(self._finishCb, self.poll)
        notify.addErrback(self._finishCb, self.poll)
        if self.messages:
            self.sendMessages([])

    def setUser(self, user):
        self.user = user

    def _finishCb(self, _, chan):
        if self.poll == chan:  # Precaution left from old version...
            self.poll = None

    def sendMessages(self, messages):
        if len(self.messages) >= 100:
            self.messages = messages
        else:
            self.messages += messages

        if self.poll is not None:
            self.poll.setHeader('Content-type', 'application/json')
            self.poll.setHeader('Pragma', 'no-cache')
            self.poll.setHeader(
                'Cache-Control',
                'no-store, no-cache, must-revalidate, max-age=0')
            json.dump(self.messages, self.poll)
            self.poll.finish()
            self.poll = None
            self.ts = None
            self.messages = []  # TODO do not clear messages before
            # poll has finished with success.  We
            # may need them to resend.  Or we
            # should store them elsewhere...

    def error(self, error):
        self.sendMessages([{
            'cmd': 'error',
            'message': error
        }])

    def flush(self):
        self.sendMessages([])

    def close(self, session):
        self.sendMessages([{'cmd': 'bye'}])

        for group in self.groups.keys():
            Group.groups[group].leave(self)
        del Channel.channels[session.uid]

    @classmethod
    def gc(cls):
        ts = time.time()
        for channel in cls.channels.itervalues():
            if (channel.ts is not None) and (channel.ts + channel.to <= ts):
                channel.flush()

    @staticmethod
    def runGc(reactor):
        try:
            Channel.gc()
        except:
            log.err()
        finally:
            reactor.callLater(GC_PERIOD, Channel.runGc, reactor)

registerAdapter(Channel, server.Session, IChannel)


class History:
    buf = None
    # Store only particular commands in history.
    # So we do not login and logout images for user privacy.
    cmdFilter = []

    def __init__(self, size=HISTORY_SIZE):
        self.buf = deque([], size)
        self.cmdFilter = ['say', 'me']

    def message(self, msg):
        if msg['cmd'] in self.cmdFilter:
            self.buf.append(msg)

    def __iter__(self):
        return self.buf.__iter__()


######################################################################
#
# Pages

class Login(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()

        nickname = request.args['name'][0]
        group = Group.groups.get(request.args['group'][0])

        if group is None:
            return json.dumps({'error': 'Group does not exist'})

        # check if name is valid
        valid = True
        try:
            nickname = resourceprep.prepare(nickname.decode('utf-8'))
            if not VALID_NICK.match(nickname):
                valid = False
            if len(nickname) > 18:
                valid = False
        except:
            valid = False
        if not valid:
            return json.dumps([{
                'cmd': 'error',
                'message': u"Invalid nickname '%s'" % (nickname,)
            }])

        roster = {'users': group.channels.keys()}

        chan = IChannel(session)

        group.join(chan, nickname)

        return json.dumps(roster)


class Logout(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        chan = IChannel(session)

        chan.close()
        session.expire()

        return 'OK'


class Post(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        chan = IChannel(session)
        msg = request.args.get('message', ['Error'])[0].strip()
        group = Group.groups.get(request.args.get('group', [None])[0])

        if group is None:
            return "Error: group not found"

        nickname = chan.groups.get(group.name)
        if nickname:
            if msg.startswith("/me "):
                message = {'cmd': 'me',
                           'user': nickname,
                           'message': msg[4:]
                           }
            else:
                message = {'cmd': 'say',
                           'user': nickname,
                           'message': msg
                           }

            group.broadcast(message)
            return "OK"
        else:
            request.setResponseCode(403)
            return "403 You are not logged in.\n"


class Poll(Resource):
    isLeaf = True

    def render_GET(self, request):
        return ''

    def render_POST(self, request):
        chan = IChannel(request.getSession())
        chan.setPoll(request)
        return server.NOT_DONE_YET


######################################################################
#
# Setup site
#

# Create test group
test = Group('test')
test.subject = "Testing group"

root = static.File("static/")

ajax = static.File("static/no-such-file")

root.putChild("ajax", ajax)

ajax.putChild("poll", Poll())
ajax.putChild("post", Post())
ajax.putChild("login", Login())
ajax.putChild("logout", Logout())

site = server.Site(root)
