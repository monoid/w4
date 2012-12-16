from twisted.web.http import Request, HTTPChannel, HTTPFactory
import json
import time
import sha
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
            self.poll.setHeader('Content-type', 'text/json')
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


def runGc(reactor):
    Channel.gc()
    reactor.callLater(TIMEOUT, runGc, reactor)


Channel.cid = 0
Channel.channels = {}

# Users by cookie.
# Currently cookie is username, later we use something more secure
users = {}

class W4WebRequest(Request):
    # def __init__(self, channel, queued, reactor=reactor):
    #     Request.__init__(self, channel, queued)
    #     self.reqctor = reactor

    def process(self):
        if self.path == '/ajax/poll':
            chan = self.ensureChannel(True)
            if chan is not None:
                chan.setPoll(self)
        elif self.path == '/ajax/post':
            user = users.get(self.getCookie('auth'), None)
            if user:
                message = "%s: %s" % (user.name, self.args.get('message', ['Error'])[0])
                for chan in Channel.channels.values():
                    chan.sendMessages([message])
                self.write('OK')
            else:
                # TODO: proper code
                self.setResponseCode(403)
                self.write("403 You are not logged in.\n")
            self.finish()
        elif self.path == '/ajax/login':
            chan = self.ensureChannel()
            user = User(self.args['name'][0])
            users[user.name] = user
            chan.setUser(user)
            self.addCookie('auth', user.name)
            self.write('OK')
            self.finish()
        elif self.path == '/ajax/logout':
            del users[self.getCookie('auth')]
            self.write('OK')
            self.finish()
        else:
            self.setResponseCode(404, "Not found")
            self.write("404 Not found\n")
            self.finish()

    def ensureChannel(self, poll=False):
        cid = self.getCookie('chan')
        if not cid or not Channel.channels.get(cid, False):
            # Create new channel
            Channel.cid += 1
            cid = sha.sha(SALT+str(Channel.cid)+str(self.getClientIP() or '')+str(time.time())).hexdigest()[-24:]
            ch = Channel(cid)
            self.addCookie('chan', cid);
            if poll:
                ch.setPoll(self)
                ch.sendMessages([])
                return None
            else:
                return ch
        else:
            return Channel.channels[cid]
            

class W4WebChannel(HTTPChannel):
    requestFactory = W4WebRequest

class W4WebFactory(HTTPFactory):
    protocol = W4WebChannel
