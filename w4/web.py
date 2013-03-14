from twisted.application import internet
from twisted.python.components import registerAdapter
from twisted.web import static, server
from twisted.web.resource import Resource
from twisted.words.protocols.jabber.xmpp_stringprep import resourceprep
from zope.interface import Interface, Attribute, implements

from .groups import Group, BaseChannel
from .xmpp import VALID_NICK
from .ifaces import IChannel

import json
import time

SESSION_TIMEOUT = 300     # Ten minutes
POLL_TIMEOUT = 120-0.2    # Almost two minutes
GC_PERIOD = 10            # Half minute


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


class HTTPChannel(BaseChannel):
    implements(IChannel)
    messages = None
    poll = None
    user = None
    ts = None
    to = POLL_TIMEOUT

    # Class attribute
    channels = {}

    def __init__(self, session):
        BaseChannel.__init__(self)
        self.messages = [{'cmd': 'ping'}]  # Force request completion
                                           # to set session cookie.
        HTTPChannel.channels[session.uid] = self
        self.uid = session.uid

        self.ts = time.time()

        def onExpire():
            self.close()

        session.notifyOnExpire(onExpire)
        session.sessionTimeout = SESSION_TIMEOUT

    def setPoll(self, poll):
        if self.poll:
            poll.setResponseCode(403) # TODO
            poll.setHeader('Content-type', 'application/json')
            json.dump([{
                'cmd': 'error',
                'type': 'duplicate-poll',
                'message': "It seems you opened chat in multiple windows..."
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

    def sendInitialInfo(self, group):
        hist = list(group.history)
        if group.subject:
            hist += [{'cmd': 'subject',
            'group': group.name,
            'message': group.subject
            }]

        self.sendMessages(hist)
        # Roster is returned as reply to login request... TODO FIXME

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

    def error(self, error, group=None):
        self.sendMessages([{
            'cmd': 'error',
            'group': group,
            'message': error
        }])

    def flush(self):
        self.sendMessages([])

    def close(self):
        self.sendMessages([{'cmd': 'bye'}])
        BaseChannel.close(self)
        del HTTPChannel.channels[self.uid]

    @classmethod
    def gc(cls):
        ts = time.time()
        for channel in cls.channels.itervalues():
            if (channel.ts is not None) and (channel.ts + channel.to <= ts):
                channel.flush()

registerAdapter(HTTPChannel, server.Session, IChannel)



######################################################################
#
# Pages

class Login(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()

        nickname = request.args['name'][0]
        group = Group.find(request.args['group'][0])

        if group is None:
            return json.dumps([{
                'cmd':'error',
                'group': group,
                'message': 'Group does not exist'
            }])

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
                'group': group,
                'message': u"Invalid nickname '%s'" % (nickname,)
            }])

        roster = {'users': group.users()}

        chan = IChannel(session)

        group.join(chan, nickname)

        # FIXME This should be done in a HTTPChannel.sendInitialInfo method.
        return json.dumps(roster)


class Logout(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        session.expire()
        return 'OK'


class Post(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        chan = IChannel(session)
        msg = request.args.get('message', ['Error'])[0].decode('utf-8').strip()
        group = Group.find(request.args.get('group', [None])[0])

        if group is None:
            return "Error: group not found"

        nickname = chan.groups.get(group.name).nick
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


###########################################################################
class W4ChanGcService(internet.TimerService):
    """ Service for gc'ing channels.
    """
    def __init__(self, interval=GC_PERIOD):
        internet.TimerService.__init__(self, interval, self._chanGc)

    def _chanGc(self):
        HTTPChannel.gc()

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
