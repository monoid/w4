from twisted.words.protocols.jabber.jid import JID
from collections import deque
import time

HISTORY_SIZE = 10

SESSION_TIMEOUT = 300     # Ten minutes
POLL_TIMEOUT = 120-0.2    # Almost two minutes
GC_PERIOD = 10            # Half minute



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


# TODO: group should have an ACL.  Even public group has an ACL where
# its owners are listed.
class Group:
    name = None
    public = True
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
        if self.public:
            if nickname in self.channels:
                if self.channels[nickname].channel == chan:
                    # returning user with same nickname.
                    return True
                else:
                    chan.error("Nickname exists.", group=self.name)
                    return False

            # Leave group if the channel have been logged before with
            # different names
            if self.name in chan.groups:
                if chan.groups[self.name] != nickname:
                    self.leave(chan)

            chan.groups[self.name] = self.channels[nickname] = MUCUser(self, nickname, chan)

            chan.sendInitialInfo(self)

            self.broadcast({
                'cmd': 'join',
                'user': nickname
            })
            return True
        else:
            # TODO: check ACL
            chan.error('Access denied', self, group=self.name)
            return False

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
        message['ts'] = int(1000*time.time())
        message['group'] = self.name
        self.history.message(message)
        for usr in self.channels.values():
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

    # Mapping of group name -> nick.
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

