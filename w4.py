from twisted.web.http import Request, HTTPChannel, HTTPFactory
import json

class User:
    name = None
    messages = None
    poll = None

    def __init__(self, name):
        self.name = name
        self.messages = []

    def setPoll(self, poll):
        # if self.poll is not None:
        #     self.poll.finish()
        self.poll = poll
        notify = self.poll.notifyFinish()
        notify.addCallback(self._finishCb, self.poll)
        notify.addErrback(self._finishCb, self.poll)

    def _finishCb(self, ignore, chan):
        if self.poll == chan:
            self.poll = None

    def sendMessages(self, messages):
        if len(self.messages) >= 100:
            self.messages = messages
        else:
            self.messages += messages
        if self.poll is not None:
            self.poll.setHeader('Content-type', 'text/json')
            json.dump(messages, self.poll)
            self.poll.finish()
            self.poll = None
            self.messages = [] # TODO do not clear messages before
            # poll has finished with success.  We
            # may need them to resend.  Or we
            # should store them elsewhere.

# Users by cookie.
# Currently cookie is username, later we use something more secure
users = {}

class W4WebRequest(Request):
    # def __init__(self, channel, queued, reactor=reactor):
    #     Request.__init__(self, channel, queued)
    #     self.reqctor = reactor

    def process(self):
        if self.path == '/ajax/poll':
            user = users.get(self.getCookie('auth'), None)
            if user:
                # TODO: decouple polling from user to allow anonymous polling.
                # It depends on group config.  Bug we have no groups yet.
                user.setPoll(self)
            else:
                # TODO not allowed
                self.setResponseCode(403)
                self.write("403 You are not logged in.\n")
                self.finish()
        elif self.path == '/ajax/post':
            user = users.get(self.getCookie('auth'), None)
            if user:
                message = "%s: %s" % (user.name, self.args.get('message', ['Error'])[0])
                for user in users.values():
                    user.sendMessages([message])
                self.write('OK')
            else:
                # TODO: proper code
                self.setResponseCode(403)
                self.write("403 You are not logged in.\n")
            self.finish()
        elif self.path == '/ajax/login':
            user = User(self.args['name'][0])
            users[user.name] = user
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

class W4WebChannel(HTTPChannel):
    requestFactory = W4WebRequest

class W4WebFactory(HTTPFactory):
    protocol = W4WebChannel
