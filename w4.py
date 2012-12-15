from twisted.web.http import Request, HTTPChannel, HTTPFactory
import json

class User:
    name = None

    def __init__(self, name):
        self.name = name

# TODO: we have to create a random id for each subscriber And use it
# to avoid missing messages...  Or is it enough to add increasing id
# for each message?
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

    def setPoll(self, poll):
        if self.poll:
            print 'setPoll: closing old poll'
            self.poll.finish()
        self.poll = poll
        print 'setPoll: set new poll'
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
        print "Sending %s to %s" % (messages, self.cid)
        if len(self.messages) >= 100:
            self.messages = messages
        else:
            self.messages += messages
        print self.poll
        if self.poll is not None:
            print 'Messages: %s' % (self.messages,)
            self.poll.setHeader('Content-type', 'text/json')
            json.dump(self.messages, self.poll)
            self.poll.finish()
            self.poll = None
            self.messages = [] # TODO do not clear messages before
            # poll has finished with success.  We
            # may need them to resend.  Or we
            # should store them elsewhere...

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
        print 'HHHHHHHHHH'+self.path
        if self.path == '/ajax/poll':
            chan = self.ensureChannel(True)
            if chan is not None:
                print "Ajax poll", chan, self
                chan.setPoll(self)
            else:
                print "chan is None"
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
        print "cookie %s" % (cid,)
        if not cid or not Channel.channels.get(cid, False):
            # Create new channel
            Channel.cid += 1
            cid = str(Channel.cid)
            print 'Creating cookie %s' % (cid,)
            if poll:
                self.addCookie('chan', cid)
                self.setHeader('Content-type', 'text/json')
                self.write('[]')
                self.finish()
            return Channel(cid)
        else:
            return Channel.channels[cid]
            

class W4WebChannel(HTTPChannel):
    requestFactory = W4WebRequest

class W4WebFactory(HTTPFactory):
    protocol = W4WebChannel
