from twisted.application import service, internet
from twisted.python.components import registerAdapter
from twisted.python import log

from .groups import Group, Groupset
from w4 import web
from w4 import xmpp


class W4HistService(service.Service):
    """ Service for loading and story history on start and stop.
    """
    histfile = None

    def __init__(self, groupset, histfile):
        self.groupset = groupset
        self.histfile = histfile

    def startService(self):
        service.Service.startService(self)
        # try to load history
        try:
            with open(self.histfile, "rb") as inf:
                self.groupset.loadGroups(inf)
        except IOError:
            pass

    def stopService(self):
        service.Service.stopService(self)
        try:
            with open(self.histfile, "wb") as outf:
                self.groupset.saveGroups(outf)
        except IOError:
            log.err()


AUTOSAVE_PERIOD = 10 * 60  # 10 minutes


class W4AutosaveService(internet.TimerService):
    """ Service for periodic storing history.
    """
    def __init__(self, groupset, histfile, interval=AUTOSAVE_PERIOD):
        internet.TimerService.__init__(self, interval, self._saveHist)
        self.groupset = groupset
        self.histfile = histfile

    def _saveHist(self):
        try:
            with open(self.histfile, "wb") as outf:
                self.groupset.saveGroups(outf)
        except IOError:
            log.err()


class W4Service(service.MultiService):
    def __init__(self, groupset, histfile):
        service.MultiService.__init__(self)

        exitsave = W4HistService(groupset, histfile)
        exitsave.setServiceParent(self)

        autosave = W4AutosaveService(groupset, histfile)
        autosave.setServiceParent(self)

        changc = web.W4ChanGcService()
        changc.setServiceParent(self)


def buildApp(application, config):
    groupset = Groupset()

    service = W4Service(groupset, config['history'])
    service.setServiceParent(application)

    server = internet.TCPServer(config['port'], web.buildSite(groupset))
    server.setServiceParent(application)

    xmpp.buildXMPPApp(config['host'],
        ('tcp:5269:interface=%s' % (config['host'],)),
        config['secret'],
        groupset,
        application)

    # Create test group
    test = Group('test', config['host'], groupset)
    test.subject = "Testing group"

    return application
