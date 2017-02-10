import sys, importlib
from core import forms

def loadModule(name):
    module = "apps." + name + ".display"
    try:
        return sys.modules[module]
    except KeyError:
        pass
    try:
        return importlib.import_module(module, '')
    except ImportError:
        return None

def loadApp(name, keys, values):
    module = loadModule(name)
    args = dict(zip(keys,values))

    if module:
        return getattr(module, "load")(args)
    return {}

#def devices():
#    return {"apps" : getApps()}, forms.AddNewDeviceForm()

def settings():
    return {}, forms.settingsForm()

def playbook():
    return {}, None

def triggers():
    return {}, forms.addNewTriggerForm()
