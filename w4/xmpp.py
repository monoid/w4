from twisted.application import strports
from twisted.words.protocols.jabber import jid
from twisted.words.xish import domish
from wokkel import component, disco, iwokkel, muc, server, xmppim
from zope.interface import implements

from .groups import Group, BaseChannel
from .ifaces import IChannel

import re
from datetime import datetime

LOG=True

VALID_NICK = re.compile(r'^\b.+\b$', re.UNICODE)

def resolveGroup(frm):
    """
    :rtype : tuple
    """
    j = frm if isinstance(frm, jid.JID) else jid.JID(frm)
    group = j.user
    nick = j.resource
    return group, nick


class OurUserPresence(muc.UserPresence):
    """ Our UserPresence implementation with correct toElement method.
    """

    def toElement(self):
        """ :rtype domish.Element
        """
        element = muc.UserPresence.toElement(self)
        emuc = element.addElement((muc.NS_MUC_USER, 'x'))
        item = emuc.addElement((muc.NS_MUC_USER, 'item'))
        item['affiliation'] = self.affiliation
        item['role'] = self.role
        for s in self.mucStatuses:
            emuc.addElement((muc.NS_MUC_USER, 'status'))['code'] = str(s)
        return element


class XMPPChannel(BaseChannel):
    implements(IChannel)
    # User's original JID
    jid = None
    # Component for sending messages
    comp = None
    # Initialization complete
    # TODO bug: it should be complete for each group separately.
    # It requires refactoring: sendHistory method.
    complete = None

    # Class attribute
    jids = {}

    def __init__(self, j, comp):
        BaseChannel.__init__(self)
        self.jid = j
        self.comp = comp
        self.complete = False

        XMPPChannel.jids[self.getJidStr()] = self

    def getJidStr(self):
        """ :rtype unicode
        """
        return self.jid.full()

    def sendMessages(self, msgs):
        if not self.complete:
            return

        for m in msgs:
            cmd = m['cmd']

            if cmd == 'say':
                gr = Group.find(m['group'])
                reply = muc.GroupChat(self.jid, gr.userJid(m['user']),
                    body=unicode(m['message']))
                self.comp.send(reply.toElement())
            elif cmd == 'me':
                gr = Group.find(m['group'])
                reply = muc.GroupChat(self.jid, gr.userJid(m['user']),
                    body=unicode(u'/me '+m['message']))
                self.comp.send(reply.toElement())
            elif cmd == 'join':
                gr = Group.find(m['group'])
                reply = OurUserPresence(recipient=self.jid,
                    sender=gr.userJid(m['user']),
                    available=True)
                reply.role='participant'
                reply.affiliation='member'
                self.comp.send(reply.toElement())
            elif cmd == 'leave':
                gr = Group.find(m['group'])
                reply = OurUserPresence(recipient=self.jid,
                    sender=gr.userJid(m['user']),
                    available=False)
                usr = self.groups[m['group']]
                if usr.nick == m['user']:
                    reply.mucStatuses.add(110)
                reply.role = 'none'
                reply.affiliation = 'member'
                self.comp.send(reply.toElement())

    def error(self, error, group=None):
        # TODO
        pass

    def flush(self):
        """ Do nothing as we do not buffer messages.
        """
        pass

    def close(self):
        BaseChannel.close(self)
        del XMPPChannel.jids[self.jid.full()]


class PresenceHandler(xmppim.PresenceProtocol):
    def availableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)

        gr = Group.find(group)

        if gr is None:
            reply = domish.Element(('jabber.client', 'presence'))
            reply['to'] = presence.sender.full()
            reply['from'] = presence.recipient.full()
            reply['type'] = 'error'

            x = domish.Element((muc.NS_MUC, 'x'))
            reply.addChild(x)

            err = domish.Element((muc.NS_MUC, 'error'))
            err['by'] = presence.recipient.userhost()
            err['type'] = 'cancel'
            reply.addChild(err)

            na = domish.Element(('urn:ietf:params:xml:ns:xmpp-stanzas',
                'not-allowed'))
            err.addChild(na)

            self.send(reply)
            return

        groupjid = gr.groupJid()

        # Validate nickname
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

        users = gr.users()

        if presence.sender.full() in XMPPChannel.jids:
            ch = XMPPChannel.jids[presence.sender.full()]
        else:
            ch = XMPPChannel(presence.sender, self.parent)

        if gr.name in ch.groups:
            # We are already in the group, it just status changed to
            # 'Away' or something like this.
            # TODO broadcast status...
            return

        gr.join(ch, nick)

        for un in users:
            reply = domish.Element(('jabber.client', 'presence'))

            reply['from'] = gr.userJid(un).full()
            reply['to'] = ch.getJidStr()

            x = domish.Element((muc.NS_MUC_USER, 'x'))
            item = domish.Element((muc.NS_MUC_USER, 'item'))
            item['affiliation'] = 'member'
            item['role'] = 'participant'

            x.addChild(item)
            reply.addChild(x)
            self.send(reply)

        # Send self name to user with status code 110
        reply = domish.Element(('jabber.client', 'presence'))

        reply['from'] = ch.jidInGroup(gr.name).full()
        reply['to'] = presence.sender.full()

        x = domish.Element((muc.NS_MUC_USER, 'x'))
        item = domish.Element((muc.NS_MUC_USER, 'item'))
        item['affiliation'] = 'member'
        item['role'] = 'participant'

        status = domish.Element((muc.NS_MUC_USER, 'status'))
        status['code'] = '110'

        x.addChild(item)
        x.addChild(status)
        reply.addChild(x)
        self.send(reply)


        # Send history if user needs it.
        for msg in gr.history:
            reply = muc.GroupChat(presence.sender,
                gr.userJid(msg['user']),
                body=unicode(msg['message']))

            ts = datetime.fromtimestamp(int(msg['ts']/1000)).isoformat() # TODO: Z

            self.send(reply.toElement(ts))

        # Send room subject
        reply = muc.GroupChat(presence.sender, gr.jid, subject=gr.subject)

        self.send(reply.toElement())

        ch.complete = True

    def unavailableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)
        gr = Group.find(group)

        if gr and nick in gr.channels:
            ch = gr.channels[nick].channel
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
        if frm in XMPPChannel.jids and group in XMPPChannel.jids[frm].groups:
            ch = XMPPChannel.jids[frm]
            nick = ch.groups[group].nick

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
            gr = Group.find(group)
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
            items = [disco.DiscoItem(gr.groupJid(), name=gr.name)
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
