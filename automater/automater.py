import logging


class Job:
  def __init__(self, name, config, logger=logging.getLogger()):
    self.name = name
    self.config = config
    self.logger = logger
    self.ret = None

  def __hash__(self):
    return hash((self.name, self.config))

  def __repr__(self):
    return '{}({}, {})'.format(self.__class__.__name__, self.name, self.config)

  def __str__(self):
    return self.__repr__()


class AsyncJob(Job):
  def __init__(self, name, config, logger=logging.getLogger()):
    super().__init__(name, config, logger=logger)

  def poll(self):
    raise NotImplementedError()


class ConsoleJob(Job):
  def __init__(self, name, config, logger=logging.getLogger()):
    super().__init__(name, config, logger=logger)


class CondorJob(Job):
  def __init__(self, name, config, logger=logging.getLogger()):
    super().__init__(name, config, logger=logger)

