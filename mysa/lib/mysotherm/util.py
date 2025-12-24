# Quacks like a dict and an object
# (from https://github.com/dlenski/wtf/blob/master/wtf.py#L10C1-L19C1)
class slurpy(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(*e.args) from e
    def __setattr__(self, k, v):
        self[k]=v
