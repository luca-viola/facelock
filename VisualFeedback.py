import abc


class VisualFeedback(object, metaclass=abc.ABCMeta):
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

  @abc.abstractmethod
  def critical(self):
    pass

  @abc.abstractmethod
  def busy(self):
    pass
