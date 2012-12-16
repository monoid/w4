# -*- mode: python -*-

from twisted.application import service, internet
from twisted.internet import reactor

import w4

PORT = 8765

application = service.Application("W4 chat")

factory = w4.W4WebFactory()
server = internet.TCPServer(PORT, factory)
server.setServiceParent(application)

w4.runGc(reactor)
