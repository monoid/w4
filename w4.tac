# -*- mode: python -*-

from twisted.application import service, internet
from twisted.internet import reactor

import w4

PORT = 8765

application = service.Application("W4 chat")

service = w4.W4Service("history.pickle")
service.setServiceParent(application)

server = internet.TCPServer(PORT, w4.site)
server.setServiceParent(application)

w4.Channel.runGc(reactor)
