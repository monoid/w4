from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.xmpp_stringprep import resourceprep

from collections import deque
import time
import re
from wokkel import disco

HISTORY_SIZE = 10

SESSION_TIMEOUT = 300     # Ten minutes
GC_PERIOD = 10            # Half minute

VALID_NICK_REGEX = re.compile(r'^\b.+\b$', re.UNICODE)


class History:
    buf = None
    # Store only particular commands in history.
    # So we do not login and logout images for user privacy.
    cmdFilter = []

    def __init__(self, size=HISTORY_SIZE, hist=()):
        self.buf = deque(hist, size)
        self.cmdFilter = ['say', 'me']

    def message(self, msg):
        if msg['cmd'] in self.cmdFilter:
            self.buf.append(msg)

    def __iter__(self):
        return self.buf.__iter__()

class PresenceException(Exception):
    tag = ''
    stanzaType = ''


class InvalidNickException(PresenceException):
    tag = 'jid-malformed'
    stanzaType = 'modify'


class NickConflictException(PresenceException):
    tag = 'conflict'
    stanzaType = 'cancel'


class RegistrationRequiredException(PresenceException):
    tag = 'registration-required'
    stanzaType = 'cancel'


# TODO: group should have an ACL.  Even public group has an ACL where
# its owners are listed.
class Group:
    name = None
    public = True
    # Map nick -> MUCUser
    channels = None
    history = None
    subject = None
    jid = None

    # Class attribute
    groups = {}

    def __init__(self, name, host='ibhome.mesemb.ru'):
        self.name = name
        self.channels = {}
        self.history = History()
        self.jid = JID(tuple=(self.name, host, None))

        Group.groups[name] = self

    def groupJid(self):
        """ :rtype JID
        """
        return self.jid

    def userJid(self, nick):
        """ :rtype JID
        """
        return JID(tuple=(self.jid.user, self.jid.host, nick))

    def users(self):
        """ :rtype list
        """
        return self.channels.keys()

    def join(self, chan, nickname):
        # Check nick validity
        try:
            nickname = resourceprep.prepare(nickname.decode('utf-8'))
            if not nickname or not VALID_NICK_REGEX.match(nickname):
                raise InvalidNickException(nick=nickname,
                                           xmpp=('urn:ietf:params:xml:ns:xmpp-stanzas', 'jid-malformed'))
            if len(nickname) > 18:
                raise InvalidNickException(nick=nickname,
                                           reason="Nickname too long",
                                           xmpp=('urn:ietf:params:xml:ns:xmpp-stanzas', 'jid-malformed'))
        except UnicodeError:
            raise InvalidNickException(nick=nickname)


        if self.public:
            if nickname in self.channels:
                if self.channels[nickname].channel == chan:
                    chan.sendSecondaryInfo(self)
                    return True
                else:
                    raise NickConflictException()

            # Leave group if the channel have been logged before with
            # different names
            if self.name in chan.groups:
                if chan.groups[self.name] != nickname:
                    self.leave(chan)

            chan.groups[self.name] = self.channels[nickname] = MUCUser(self, nickname, chan)

            chan.sendInitialInfo(self)

            self.broadcast({
                'cmd': 'join',
                'user': nickname,
                'except': nickname
            })
            return True
        else:
            raise RegistrationRequiredException()

    def leave(self, chan):
        nickname = chan.groups[self.name].nick
        if nickname in self.channels:
            self.broadcast({
                'cmd': 'leave',
                'user': nickname
            })
            del self.channels[nickname]
            del chan.groups[self.name]
            return True
        else:
            # TODO exception
            return False

    def broadcast(self, message):
        message['ts'] = int(1000 * time.time())
        message['group'] = self.name
        self.history.message(message)
        for usr in self.channels.values():
            if message.get('except', None) == usr.nick:
                continue
            else:
                usr.channel.sendMessages([message])

    def __getinitargs__(self):
        return self.name, self.jid.host

    def __getstate__(self):
        return {
            'name': self.name,
            'public': self.public,
            'history': list(self.history),
            'subject': self.subject
        }

    def __setstate__(self, state):
        self.name = state['name']
        self.public = state['public']
        self.history = History(hist=state['history'])
        self.subject = state['subject']

    def getDiscoFeatures(self):
        return map(disco.DiscoFeature,
                   ['http://jabber.org/protocol/muc',
                   'muc_unmoderated',
                   'muc_open',
                   'muc_persistent',
                   'muc_unsecured'])

    @classmethod
    def find(cls, groupname):
        return cls.groups.get(groupname)

    @classmethod
    def saveGroups(cls, outf):
        import pickle
        pickle.dump(cls.groups.values(), outf)

    @classmethod
    def loadGroups(cls, inf):
        import pickle
        groups = pickle.load(inf)
        for group in groups:
            cls.groups[group.name] = group


class BaseChannel():
    """ Base implementation of channel with utility methods.
    """

    # Mapping of group name -> MUCUser.
    groups = None

    def __init__(self):
        self.groups = {}

    def getNick(self, group):
        if isinstance(group, Group):
            group = group.name
        return self.groups.get(group, None)

    def jidInGroup(self, group):
        """ :rtype JID
        """
        return self.groups[group].jid

    def close(self):
        for group in self.groups.keys():
            Group.find(group).leave(self)


class MUCUser():
    """ User in a MUC.
    """

    # Group user in
    group = None
    # User's nick in the group
    nick = None
    # User's channel (e.g. HTTPChannel or XMPPChannel)
    channel = None
    # User's jid (group.name@host/nick)
    jid = None

    def __init__(self, group, nick, channel):
        self.group = group
        self.nick = nick
        self.channel = channel

        gj = group.groupJid()
        self.jid = JID(tuple=(gj.user, gj.host, nick))

    def getJid(self):
        """ User's jid (group.name@host/nick).
            :rtype JID
        """
        return self.jid
