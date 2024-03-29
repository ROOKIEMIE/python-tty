def injector(service):
    def class_decorator(cls):
        original_init = cls.__init__

        def modified_init(self, *args, **kwargs):
            self.service = service
            original_init(self, *args, **kwargs)

        cls.__init__ = modified_init
        return cls

    return class_decorator
