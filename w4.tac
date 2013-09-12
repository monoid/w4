# -*- mode: python -*-

from twisted.application import service, internet
from twisted.internet import reactor

import w4
import w4.groups
import w4.xmpp


PORT = 8765              # Webserver port
HOST = 'yourdomain.tld'  # Your domain name for XMPP
SECRET = 'av3fad'

application = service.Application("W4 chat")

service = w4.W4Service("history.pickle")
service.setServiceParent(application)

server = internet.TCPServer(PORT, w4.site)
server.setServiceParent(application)

w4.xmpp.buildXMPPApp(HOST,
    ('tcp:5269:interface=%s' % (HOST,)),
    SECRET,
    application)

# Create test group
test = w4.groups.Group('test', HOST)
test.subject = "Testing group"
