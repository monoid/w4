from twisted.application import strports
from twisted.internet import defer
from twisted.words.protocols.jabber import jid
from wokkel import component, disco, iwokkel, server, xmppim
from zope.interface import implements

from .groups import Group

import re

LOG=True

VALID_NICK = re.compile(r'^\S.*\S$', re.UNICODE)

def resolveGroup(frm):
    j = frm if isinstance(frm, jid.JID) else jid.JID(frm)
    group = j.user
    nick = j.resource
    return (group, nick)


class XMPPChannel():
    jid = None

    def __init__(self, j):
        self.jid = j
        self.groups = {}

    def sendMessages(self, msgs):
        pass

    def error(self, error, group=None):
        pass

    def flush(self):
        pass

    def close(self):
        pass


class DiscoHandler(disco.DiscoHandler):
    pass

class PresenceHandler(xmppim.PresenceProtocol):
    def availableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)
        gr = Group.groups.get(group)
        ch = XMPPChannel(presence.sender)
        gr.join(ch, nick)

    def unavailableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)
        gr = Group.groups.get(group)

        ch = gr.channels.get(nick)
        gr.leave(ch)


class ChatHandler(xmppim.MessageProtocol):
    implements(iwokkel.IDisco)

    def onMessage(self, message):
        if message.getAttribyte('type') == 'error':
            return

        if message.getAttribyte('type') != 'groupchat':
            return

        if message.body and unicode(message.body):
            print message.toXml()  # DEBUG

        group, nick = resolveGroup(message.getAttribute('to'))
        gr = Group.groups.get(group)
        gr.broadcast({
            'cmd': 'message',
            'from': nick,
            'message': unicode(message.body)
        })

    def getDiscoInfo(self, req, target, ni):
        print "getDiscoInfo"
        group, nick = resolveGroup(req)
        return defer.succeed([])

    def getDiscoItems(self, req, target, ni):
        print "getDiscoItems"
        return defer.succeed([])


#########################################################################
def buildXMPPApp(domain, port, secret, application):
    router = component.Router()
    serverService = server.ServerService(router, domain=domain, secret=secret)
    serverService.logTraffic = LOG

    s2sFactory = server.XMPPS2SServerFactory(serverService)
    s2sFactory.logTraffic = LOG
    s2sService = strports.service(port, s2sFactory)
    s2sService.setServiceParent(application)

    w4Comp = component.InternalComponent(router, domain)
    w4Comp.logTraffic = LOG
    w4Comp.setServiceParent(application)

    #presenceHandler = PresenceHandler()
    #presenceHandler.setHandlerParent(w4Comp)

    #chatHandler = ChatHandler()
    #chatHandler.setHandlerParent(w4Comp)

    #discoHandler = disco.DiscoHandler()
    #discoHandler.setHandlerParent(w4Comp)

    return application
