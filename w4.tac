# -*- mode: python -*-

from twisted.application import service, internet
from twisted.internet import reactor

import w4
import w4.xmpp

PORT = 8765

application = service.Application("W4 chat")

service = w4.W4Service("history.pickle")
service.setServiceParent(application)

server = internet.TCPServer(PORT, w4.site)
server.setServiceParent(application)

w4.xmpp.buildXMPPApp('ibhome.mesemb.ru',
    'tcp:5269:interface=ibhome.mesemb.ru',
    'av3fasdb',
    application)
