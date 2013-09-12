# -*- mode: python -*-

from twisted.application import service, internet
from twisted.internet import reactor

import w4

CONFIG = {
    'port': 8765,              # Webserver port
    'host': 'yourdomain.tld',  # Your domain name for XMPP
    'secret': 'av3fad',
}

application = service.Application("W4 chat")

w4.buildApp(application, CONFIG)
