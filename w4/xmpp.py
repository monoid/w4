from twisted.application import strports
from twisted.words.protocols.jabber import jid
from twisted.words.xish import domish
from wokkel import component, disco, iwokkel, muc, server, xmppim
from zope.interface import implements

from .groups import Group

import re
from datetime import datetime

LOG=True

VALID_NICK = re.compile(r'^\S.*\S$', re.UNICODE)

def resolveGroup(frm):
    j = frm if isinstance(frm, jid.JID) else jid.JID(frm)
    group = j.user
    nick = j.resource
    return group, nick


class OurUserPresence(muc.UserPresence):
    """ Our UserPresence implementation with correct toElement method.
    """

    def toElement(self):
        element = muc.UserPresence.toElement(self)
        emuc = element.addElement((muc.NS_MUC_USER, 'x'))
        item = emuc.addElement((muc.NS_MUC_USER, 'item'))
        item['affiliation'] = self.affiliation
        item['role'] = self.role
        for s in self.mucStatuses:
            emuc.addElement((muc.NS_MUC_USER, 'status'))['code'] = str(s)
        return element


class XMPPChannel():
    jid = None
    groups = None
    comp = None
    complete = None

    def __init__(self, j, comp):
        self.jid = j
        self.groups = {}
        self.comp = comp
        self.complete = False

    def getJid(self):
        return self.jid.full()

    def sendMessages(self, msgs):
        if not self.complete:
            return

        for m in msgs:
            cmd = m['cmd']

            if cmd == 'say':
                gr = Group.groups.get(m['group'])
                reply = muc.GroupChat(self.jid, jid.JID("%s@ibhome.mesemb.ru/%s" % (gr.name, m['user'])),
                    body=unicode(m['message']))
                self.comp.send(reply.toElement())
            elif cmd == 'me':
                gr = Group.groups.get(m['group'])
                reply = muc.GroupChat(self.jid, jid.JID("%s@ibhome.mesemb.ru/%s" % (gr.name, m['user'])),
                    body=unicode(u'/me '+m['message']))
                self.comp.send(reply.toElement())
            elif cmd == 'join':
                gr = Group.groups.get(m['group'])
                reply = OurUserPresence(recipient=self.jid,
                    sender=jid.JID("%s@ibhome.mesemb.ru/%s" % (gr.name, m['user'])),
                    available=True)
                reply.role='participant'
                reply.affiliation='member'
                self.comp.send(reply.toElement())
            elif cmd == 'leave':
                gr = Group.groups.get(m['group'])
                reply = OurUserPresence(recipient=self.jid,
                    sender=jid.JID("%s@ibhome.mesemb.ru/%s" % (gr.name, m['user'])),
                    available=False)
                if self.getJid() in gr.jids:
                    if self.groups.get(gr.name) == m['user']:
                        reply.mucStatuses.add(110)
                reply.role = 'none'
                reply.affiliation = 'member'
                self.comp.send(reply.toElement())



    def error(self, error, group=None):
        pass

    def flush(self):
        pass

    def close(self):
        pass


class PresenceHandler(xmppim.PresenceProtocol):
    def availableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)
        # Validate nickname

        groupjid = presence.recipient.userhost()

        if nick:
            if VALID_NICK.match(nick):
                pass
            else:
                "Error: incorrect nick"
        else:
            reply = domish.Element(('jabber.client', 'presence'))
            reply['to'] = presence.sender.full()
            reply['from'] = groupjid

            err = domish.Element(('jabber.client', 'error'))
            err['by'] = groupjid
            err['type'] = 'modify'

            jm = domish.Element(('urn:ietf:params:xml:ns:xmpp-stanzas', 'jid-malformed'))
            err.addChild(jm)
            reply.addChild(err)

            self.send(reply)
            return

        gr = Group.groups.get(group)
        users = gr.channels.keys()

        ch = XMPPChannel(presence.sender, self.parent)
        gr.join(ch, nick)

        for un in users:
            reply = domish.Element(('jabber.client', 'presence'))

            reply['from'] = jid.JID(tuple=(group, presence.recipient.host, un)).full()
            reply['to'] = presence.sender.full()

            x = domish.Element(('http://jabber.org/protocol/muc#user', 'x'))
            item = domish.Element(('http://jabber.org/protocol/muc#user', 'item'))
            item['affiliation'] = 'member'
            item['role'] = 'participant'

            x.addChild(item)
            reply.addChild(x)
            self.send(reply)

        # Send self name to user with status code 110
        reply = domish.Element(('jabber.client', 'presence'))

        reply['from'] = jid.JID(tuple=(group, presence.recipient.host, nick)).full()
        reply['to'] = presence.sender.full()

        x = domish.Element(('http://jabber.org/protocol/muc#user', 'x'))
        item = domish.Element(('http://jabber.org/protocol/muc#user', 'item'))
        item['affiliation'] = 'member'
        item['role'] = 'participant'

        status = domish.Element(('http://jabber.org/protocol/muc#user', 'status'))
        status['code'] = '110'

        x.addChild(item)
        x.addChild(status)
        reply.addChild(x)
        self.send(reply)


        # Send history if user needs it.
        for msg in gr.history:
            reply = muc.GroupChat(presence.sender,
                jid.JID(tuple=(group, presence.recipient.host, msg['user'])),
                body=unicode(msg['message']))

            ts = datetime.fromtimestamp(int(msg['ts']/1000)).isoformat() # TODO: Z

            self.send(reply.toElement(ts))

        # Send room subject
        reply = muc.GroupChat(presence.sender, jid.JID(groupjid), subject=gr.subject)

        self.send(reply.toElement())

        ch.complete = True

    def unavailableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)
        gr = Group.groups.get(group)

        if gr:
            ch = gr.channels.get(nick)
            if ch:
                gr.leave(ch)


class ChatHandler(xmppim.MessageProtocol):
    implements(iwokkel.IDisco)

    def onMessage(self, message):
        if message.getAttribute('type') == 'error':
            return

        if message.getAttribute('type') != 'groupchat':
            return

        group, nick = resolveGroup(message.getAttribute('to'))

        gr = Group.groups.get(group)

        frm = message.getAttribute('from')
        if frm in gr.jids:
            nick = gr.jids[frm].groups.get(group)
            gr.broadcast({
               'cmd': 'say',
               'user': nick,
               'message': unicode(message.body)
            })
        else:
            # TODO Error: not member
            pass

    def getDiscoInfo(self, req, target, ni):
        group, nick = resolveGroup(target)
        if group in Group.groups and not ni and not nick:
            gr = Group.groups[group]
            di = disco.DiscoInfo()
            di.append(disco.DiscoIdentity(u'conference', u'text', name=gr.name))
            return di
        else:
            # TODO
            return []

    def getDiscoItems(self, req, target, ni):
        group, nick = resolveGroup(target)
        if group is None:
            # Return list of groups
            items = [disco.DiscoItem(jid.JID(gr.name+"@ibhome.mesemb.ru"), name=gr.name)
                    for gr in Group.groups.values()]
            return items
        else:
            # TODO
            return []


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

    presenceHandler = PresenceHandler()
    presenceHandler.setHandlerParent(w4Comp)

    chatHandler = ChatHandler()
    chatHandler.setHandlerParent(w4Comp)

    discoHandler = disco.DiscoHandler()
    discoHandler.setHandlerParent(w4Comp)

    return application
