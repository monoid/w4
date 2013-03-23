from twisted.application import service, internet
from twisted.python.components import registerAdapter
from twisted.python import log

from .groups import Group
from .web import W4ChanGcService, site

from collections import deque


class W4HistService(service.Service):
    """ Service for loading and story history on start and stop.
    """
    histfile = None

    def __init__(self, histfile):
        self.histfile = histfile

    def startService(self):
        service.Service.startService(self)
        # try to load history
        try:
            with open(self.histfile, "rb") as inf:
                Group.loadGroups(inf)
        except IOError:
            pass

    def stopService(self):
        service.Service.stopService(self)
        try:
            with open(self.histfile, "wb") as outf:
                Group.saveGroups(outf)
        except IOError:
            log.err()


AUTOSAVE_PERIOD = 10 * 60  # 10 minutes


class W4AutosaveService(internet.TimerService):
    """ Service for periodic storing history.
    """
    def __init__(self, histfile, interval=AUTOSAVE_PERIOD):
        internet.TimerService.__init__(self, interval, self._saveHist)
        self.histfile = histfile

    def _saveHist(self):
        try:
            with open(self.histfile, "wb") as outf:
                Group.saveGroups(outf)
        except IOError:
            log.err()


class W4Service(service.MultiService):
    def __init__(self, histfile):
        service.MultiService.__init__(self)

        exitsave = W4HistService(histfile)
        exitsave.setServiceParent(self)

        autosave = W4AutosaveService(histfile)
        autosave.setServiceParent(self)

        changc = W4ChanGcService()
        changc.setServiceParent(self)
