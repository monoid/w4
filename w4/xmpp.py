from twisted.application import strports
from twisted.words.protocols.jabber import jid, error
from twisted.words.xish import domish
from wokkel import component, disco, delay, iwokkel, muc, server, xmppim
from zope.interface import implements

from .groups import Group, BaseChannel, PresenceException
from .ifaces import IChannel

import datetime

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


class Utc(datetime.tzinfo):
    """ UTC timezone implementation.
    """
    ZERO = datetime.timedelta(0)
    """ UTC timezone"""
    def utcoffset(self, dt):
        return self.ZERO
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return self.ZERO

UTC = Utc()


class GroupChat(muc.GroupChat):
    """ Groupchat message that always insert delay tag if available, and if
    legacyDelay is set, also insert legacy delay tag.

    Original implementation inserts only single tag.
    """
    def toElement(self, legacyDelay=False):
        """
        Render into a domish Element.

        @param legacyDelay: If C{True} send the delayed delivery information
        in legacy format too.
        """
        element = xmppim.Message.toElement(self)

        if self.delay:
            element.addChild(self.delay.toElement(legacy=False))
            if legacyDelay:
                element.addChild(self.delay.toElement(legacy=True))

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
        myname = self.groups[gr.name].nick
        for un in users:
            if myname == un:
                continue
            self.sendMessages([{
                'cmd': 'join',
                'group': gr.name,
                'user': un
            }])

        # Send self name to user with status code 110
        # The code is added by sendMessages
        self.sendMessages([{
            'cmd': 'join',
            'group': gr.name,
            'user': myname
        }])

        # Send history if user needs it.
        for msg in gr.history:
            reply = GroupChat(self.jid,
                              gr.userJid(msg['user']),
                              body=unicode(msg['message']))

            ts = datetime.datetime.fromtimestamp(int(msg['ts'])/1000.0, UTC)
            reply.delay = delay.Delay(ts, gr.jid)

            self.comp.send(reply.toElement(True))

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
                usr = self.groups[m['group']]
                if usr.nick == m['user']:
                    reply.mucStatuses.add(110)
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

    @classmethod
    def isMember(cls, jid, group):
        ch = cls.jids.get(jid, None)
        return ch and (group.name in ch.groups)


class PresenceHandler(xmppim.PresenceProtocol):
    def availableReceived(self, presence):
        try:
            group, nick = resolveGroup(presence.recipient)

            gr = Group.find(group)

            if gr is None:
                raise error.StanzaError('not-allowed', type='cancel')

            ch = XMPPChannel.getChannel(presence.sender, self.parent)

            if gr.name in ch.groups:
                # We are already in the group, it just status changed to
                # 'Away' or something like this.
                # TODO broadcast status...
                return
            else:
                try:
                    gr.join(ch, nick)
                except PresenceException as ex:
                    raise error.StanzaError(ex.tag, type=ex.stanzaType)
        except error.StanzaError as ex:
            reply = ex.toResponse(presence.toElement())
            self.send(reply)

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
        try:
            msgType = message.getAttribute('type')
            group, nick = resolveGroup(message.getAttribute('to'))

            gr = Group.groups.get(group)

            frm = message.getAttribute('from')

            if frm in XMPPChannel.jids and group in XMPPChannel.jids[frm].groups:
                ch = XMPPChannel.jids[frm]
                senderNick = ch.groups[group].nick

                if not nick and msgType == 'groupchat':
                    # It may be None if it is a chat state notification like 'composing'.
                    if message.body is not None:
                        gr.broadcast({
                            'cmd': 'say',
                            'user': senderNick,
                            'message': unicode(message.body)
                        })
                elif nick and msgType != 'groupchat':
                    # TODO private messaging is handled here
                    pass
                else:
                    # See Example 48
                    raise error.StanzaError('bad-request', type='modify')
            else:
                raise error.StanzaError('not-acceptable', type='cancel')
        except error.StanzaError as ex:
            reply = ex.toResponse(message)
            self.send(reply)

    def getDiscoInfo(self, req, target, ni):
        group, nick = resolveGroup(target)
        if group in Group.groups and not ni:
            gr = Group.find(group)
            if nick:
                if XMPPChannel.isMember(req.full(), gr):
                    # TODO
                    raise error.StanzaError('service-unavailable')
                else:
                    raise error.StanzaError('bad-request')
            else:
                di = [disco.DiscoIdentity(u'conference', u'text', name=gr.name)]
                for f in gr.getDiscoFeatures():
                    di.append(f)

                return di
        else:
            # TODO
            raise error.StanzaError('not-implemented')

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
