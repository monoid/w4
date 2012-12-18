from twisted.python.components import registerAdapter
from twisted.web import static, server
from twisted.web.http import Request, HTTPChannel, HTTPFactory
from twisted.web.resource import Resource
from zope.interface import Interface, Attribute, implements

import json
import time
import weakref

TIMEOUT=600 # Ten minutes


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


######################################################################

class IInited(Interface):
    inited = Attribute("Initialized flag")

class Inited:
    implements(IInited)

    def __init__(self, session):
        self.inited = False

registerAdapter(Inited, server.Session, IInited)


class IUser(Interface):
    # TODO: id
    name = Attribute("User name")

class User():
    implements(IUser)

    def __init__(self, session):
        self.name = None

User.users = {}

registerAdapter(User, server.Session, IUser)


class IChannel(Interface):
    messages = Attribute("")
    poll = Attribute("")
    user = Attribute("")
    
class Channel():
    implements(IChannel)
    messages = None
    poll = None
    user = None

    def __init__(self, session):
        self.messages = []
        Channel.channels[session.uid] = self

    def setPoll(self, poll):
        if self.poll:
            self.poll.finish()
        self.poll = poll
        notify = self.poll.notifyFinish()
        notify.addCallback(self._finishCb, self.poll)
        notify.addErrback(self._finishCb, self.poll)
        if self.messages:
            self.sendMessages([])

    def setUser(self, user):
        self.user = user

    def _finishCb(self, ignore, chan):
        if self.poll == chan: # Precaution left from old version...
            self.poll = None

    def sendMessages(self, messages):
        if len(self.messages) >= 100:
            self.messages = messages
        else:
            self.messages += messages

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
            
    def close(self, session):
        self.sendMessages([])
        del Channel.channels[session.uid]
        if self.user and self.user.name:
            del User.users[self.user.name]
            Channel.broadcast({'cmd': 'leave', 'user': self.user.name})

    @classmethod
    def ensureChannel(self, request, poll=False):
        session = request.getSession()

        inited = IInited(session)
        ch = IChannel(session)

        if not inited.inited:
            inited.inited = True
            session.sessionTimeout = 60 # DEBUG
            def onExpire():
                ch.close(session)
            exp = session.notifyOnExpire(onExpire)
            if poll:
                ch.setPoll(request)
                ch.sendMessages([])
                return None
        return ch

    @classmethod
    def broadcast(self, message):
        message['ts'] = int(1000*time.time())
        for chan in self.channels.values():
            chan.sendMessages([message])

Channel.channels = {}

registerAdapter(Channel, server.Session, IChannel)


######################################################################

class Login(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        user = IUser(session)
        user.name = request.args['name'][0]

        if user.name not in User.users:
            message = {'cmd': 'join',
                       'user': user.name
                      }
            User.users[user.name] = user
            Channel.broadcast(message)

        chan = Channel.ensureChannel(request)
        # TODO: check if name is valid
        chan.setUser(user)

        return json.dumps({'users': User.users.keys()})

class Logout(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        chan = IChannel(session)
        chan.close()
        session.expire()

        message = {'cmd': 'leave',
                   'user': user.name
                   }

        Channel.broadcast(message)

        del User.users[user.name]

        return 'OK'


class Post(Resource):
    isLeaf = True

    def render_POST(self, request):
        session = request.getSession()
        user = IUser(session)
        msg = request.args.get('message', ['Error'])[0].strip()
        if user.name:
            if msg.startswith("/me "):
                message = {'cmd': 'me',
                           'user': user.name,
                           'message': msg[4:]
                           }
            else:
                message = {'cmd': 'say',
                           'user': user.name,
                           'message': msg
                           }

            Channel.broadcast(message)
            return "OK"
        else:
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
