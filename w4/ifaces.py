from zope.interface import Attribute, Interface

class IChannel(Interface):
    """ Channel represents either HTTP or XMPP user session.
    """

    messages = Attribute("")
    poll = Attribute("")
    user = Attribute("")
    groups = Attribute("Dict of channel's group by name.")
    ts = Attribute("Poll's timestamp")
    to = Attribute("Poll's timeout")


    def getJid(self):
        """ Return user's original JID or None.
        """

    def sendMessages(self, messages):
        """ Send array of messages to channel.
        """

    def error(self, error, group=None):
        """  Send error message about group.
        """

    def flush(self):
        """ Force immediate sending of buffered messages (if any).
        """

    def close(self):
        """ Close the channel.
        """

