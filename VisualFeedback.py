import abc


class VisualFeedback(object):
  __metaclass__ = abc.ABCMeta
  
  def __init__(self, value):
    self.value = value

  @abc.abstractmethod
  def ok(self):
    pass

  @abc.abstractmethod
  def warn(self):
    pass

  @abc.abstractmethod
  def ko(self):
    pass

  @abc.abstractmethod
  def idle(self):
    pass

