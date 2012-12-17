from twisted.web import static, server
from twisted.web.http import Request, HTTPChannel, HTTPFactory
from twisted.web.resource import Resource

import json
import sha
import time
import weakref

SALT='a38a72ca6fdf3a7305ceaeb1dea1ee1ad761bc3f'

TIMEOUT=600 # Ten minutes

# TODO: add numeric id?
class User:
    name = None

    def __init__(self, name):
        self.name = name


# TODO: group should have an ACL.  Even public group has an ACL where
# its owners are listed.
class Group:
    name = None
    public = True
    channels = None
    users = None

    def __init__(self, name):
        self.name = name
        self.channels = weakref.WeakValueDictionary()
        self.users = weakref.WeakValueDictionary()

    def joinChannel(self, chan):
        if self.public:
            self.channels[chan.cid] = chan
        else:
            # TODO:
            pass

    def leaveChannel(self, chan):
        del self.channels[chan.cid]

    def joinUser(self, user):
        # TODO: notify group subscribers about user join
        if self.public:
            self.users[user.name] = user
        else:
            # TODO
            pass

    def leaveUser(self, user):
        # TODO: notify group subscribers
        del self.users[user.name]


class Channel():
    cid = None
    messages = None
    poll = None
    user = None
    ts = None # Timestamp

    def __init__(self, cid):
        self.cid = cid
        self.messages = []
        Channel.channels[cid] = self
        self.ts = time.time()

    def setPoll(self, poll):
        self.ts = time.time()
        if self.poll:
            self.poll.finish()
        self.poll = poll
        notify = self.poll.notifyFinish()
        notify.addCallback(self._finishCb, self.poll)
        notify.addErrback(self._finishCb, self.poll)
        if self.messages:
            self.sendMessages([])

    def setUser(self, user):
        self.ts = time.time()
        self.user = user

    def _finishCb(self, ignore, chan):
        if self.poll == chan: # Precaution left from old version...
            self.poll = None

    def sendMessages(self, messages):
        self.ts = time.time()
        if len(self.messages) >= 100:
            self.messages = messages
        else:
            self.messages += messages
        print self.poll
        if self.poll is not None:
            self.poll.setHeader('Content-type', 'application/json')
            self.poll.setHeader('Pragma', 'no-cache')
            self.poll.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            json.dump(self.messages, self.poll)
            self.poll.finish()
            self.poll = None
            self.messages = [] # TODO do not clear messages before
            # poll has finished with success.  We
            # may need them to resend.  Or we
            # should store them elsewhere...

    @classmethod
    def gc(self, interval=TIMEOUT):
        now = time.time()
        cnt = 0
        size = len(self.channels)
        for cid, chan in self.channels.items():
            if now - chan.ts >= interval:
                cnt += 1
                del self.channels[cid]

    @classmethod
    def ensureChannel(self, request, poll=False):
        cid = request.getCookie('chan')
        if not cid or not Channel.channels.get(cid, False):
            # Create new channel
            self.cid += 1
            cid = sha.sha(SALT+str(self.cid)+str(request.getClientIP() or '')+str(time.time())).hexdigest()[-24:]
            ch = Channel(cid)
            request.addCookie('chan', cid);
            if poll:
                ch.setPoll(request)
                ch.sendMessages([])
                return None
            else:
                return ch
        else:
            return self.channels[cid]


def runGc(reactor):
    Channel.gc()
    reactor.callLater(TIMEOUT, runGc, reactor)


Channel.cid = 0
Channel.channels = {}

# Users by cookie.
# Currently cookie is username, later we use something more secure
users = {}


######################################################################

class Login(Resource):
    isLeaf = True

    def render_POST(self, request):
        chan = Channel.ensureChannel(request)
        user = User(request.args['name'][0])
        users[user.name] = user
        chan.setUser(user)
        request.addCookie('auth', user.name)
        return "OK"

class Logout(Resource):
    isLeaf = True

    def render_POST(self, request):
        del users[request.getCookie('auth')]
        return 'OK'

class Post(Resource):
    isLeaf = True

    def render_POST(self, request):
        user = users.get(request.getCookie('auth'), None)
        if user:
            message = "%s: %s" % (user.name, request.args.get('message', ['Error'])[0])
            for chan in Channel.channels.values():
                chan.sendMessages([message])
            return "OK"
        else:
            # TODO: proper code
            request.setResponseCode(403)
            return "403 You are not logged in.\n"

class Poll(Resource):
    isLeaf = True

    def render_GET(self, request):
        chan = Channel.ensureChannel(request, True)
        if chan:
            chan.setPoll(request)
        return server.NOT_DONE_YET

    render_POST = render_GET


######################################################################

root = static.File("static/")

ajax = static.File("static/no-such-file")

root.putChild("ajax", ajax)

ajax.putChild("poll", Poll())
ajax.putChild("post", Post())
ajax.putChild("login", Login())
ajax.putChild("logout", Logout())

site = server.Site(root)
