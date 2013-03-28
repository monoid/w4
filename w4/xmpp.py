from twisted.application import strports
from twisted.words.protocols.jabber import jid, error
from twisted.words.xish import domish
from wokkel import component, disco, iwokkel, muc, server, xmppim
from zope.interface import implements

from .groups import Group, BaseChannel, InvalidNickException
from .ifaces import IChannel

from datetime import datetime

LOG = True



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

    # Class attribute
    jids = {}

    def __init__(self, j, comp):
        BaseChannel.__init__(self)
        self.jid = j
        self.comp = comp

        XMPPChannel.jids[self.getJidStr()] = self

    def getJidStr(self):
        """ :rtype unicode
        """
        return self.jid.full()

    def sendInitialInfo(self, gr):
        users = gr.users()
        for un in users:
            reply = domish.Element(('jabber.client', 'presence'),
                                   attribs={'from': gr.userJid(un).full(),
                                            'to': self.getJidStr()})

            x = domish.Element((muc.NS_MUC_USER, 'x'))
            item = domish.Element((muc.NS_MUC_USER, 'item'),
                                  attribs={'affiliation': 'member',
                                           'role': 'participant'})

            x.addChild(item)
            reply.addChild(x)
            self.comp.send(reply)

        # Send self name to user with status code 110
        reply = domish.Element(('jabber.client', 'presence'),
                               attribs={'from': self.jidInGroup(gr.name).full(),
                                        'to': self.jid.full()})
        x = domish.Element((muc.NS_MUC_USER, 'x'))
        item = domish.Element((muc.NS_MUC_USER, 'item'),
                              attribs={'affiliation': 'member',
                                       'role': 'participant'})
        status = domish.Element((muc.NS_MUC_USER, 'status'),
                                attribs={'code': '110'})
        x.addChild(item)
        x.addChild(status)
        reply.addChild(x)
        self.comp.send(reply)

        # Send history if user needs it.
        for msg in gr.history:
            reply = muc.GroupChat(self.jid,
                                  gr.userJid(msg['user']), body=unicode(msg['message']))

            ts = datetime.fromtimestamp(int(msg['ts'] / 1000)).isoformat()  # TODO: Z

            self.comp.send(reply.toElement(ts))

        # Send room subject
        reply = muc.GroupChat(self.jid, gr.jid, subject=gr.subject)
        self.comp.send(reply.toElement())

    def sendMessages(self, msgs):
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
                                      body=unicode(u'/me ' + m['message']))
                self.comp.send(reply.toElement())
            elif cmd == 'join':
                gr = Group.find(m['group'])
                reply = OurUserPresence(recipient=self.jid,
                                        sender=gr.userJid(m['user']),
                                        available=True)
                reply.role = 'participant'
                reply.affiliation = 'member'
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

    @classmethod
    def getChannel(cls, jid, comp):
        sjid = jid.full()
        if sjid in cls.jids:
            return cls.jids[sjid]
        else:
            return XMPPChannel(jid, comp)


class PresenceHandler(xmppim.PresenceProtocol):
    def availableReceived(self, presence):
        group, nick = resolveGroup(presence.recipient)

        gr = Group.find(group)

        sender = presence.sender.full()
        recipient = presence.recipient.full()
        if gr is None:
            reply = domish.Element(('jabber.client', 'presence'),
                                   attribs={'to': sender,
                                            'from': recipient,
                                            'type': 'error'})

            x = domish.Element((muc.NS_MUC, 'x'))
            reply.addChild(x)

            err = domish.Element((muc.NS_MUC, 'error'),
                                 attribs={'by': presence.recipient.userhost(),
                                          'type': 'cacnel'})
            reply.addChild(err)

            na = domish.Element((error.NS_XMPP_STANZAS,
                                 'not-allowed'))
            err.addChild(na)

            self.send(reply)
            return

        groupjid = gr.groupJid()


        ch = XMPPChannel.getChannel(presence.sender, self.parent)

        if gr.name in ch.groups:
            # We are already in the group, it just status changed to
            # 'Away' or something like this.
            # TODO broadcast status...
            return
        else:
            try:
                gr.join(ch, nick)
            except InvalidNickException as ex:
                raise error.StanzaError('jid-malformed', type='modify')


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

            if message.body is not None:
                # It may be None if it is a chat state notification like 'composing'.
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
            for f in gr.getDiscoFeatures():
                di.append(f)

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
