#Copyright 2014 Plexxi, Inc.
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from d6message import d6msg
from dataobj import pubData, subData, dataObject
import logging
import pprint
import threading
import time


class deepSix(threading.Thread):
    def __init__(self, name, keys, inbox=None, dataPath=None):
        threading.Thread.__init__(self)

        self.name = name
        self.pp = pprint.PrettyPrinter(indent=1)
        keyList = []

        for k in keys:
            keyList.append(k)
            localk = "local." + k
            keyList.append(localk)

        keyList.append("allservices")
        keyList.append("local.allservices")

        self.keys = keyList

        self.running = True

        self.pubdata = {}
        self.subdata = {}
        self.subscriberCorrelationUuids = set()
        self.scheduuids = set()
        self.timerThreads = []

        if inbox:
            self.inbox = inbox
            self.dataPath = dataPath

        keyargs = {}
        keyargs['keys'] = self.keys

        self.publish("routeKeys", keyargs)

    def send(self, msg):
        self.log("sending msg {}".format(str(msg)))
        self.dataPath.put_nowait(msg)

    def schedule(self, msg, scheduuid, interval, callback=None):
        # logging.debug("{} scheduling msg {}".format(self.name, str(msg)))
        if scheduuid in self.scheduuids:

            if msg.type == 'pub':
                msg.updatebody(self.pubdata[msg.dataindex].get())

            self.send(msg)

            th = threading.Timer(
                interval,
                self.schedule,
                [msg, scheduuid, interval, callback])
            th.daemon = True
            self.timerThreads.append(th.start())
        else:
            logging.warn("{} scheduled a message without adding to "
                         "scheduuids".format(self.name))

    def getSubData(self, corrId, sender=""):
        if corrId in self.subdata:
            if sender:
                return self.subdata[corrId].getData(sender)
            else:
                return self.subdata[corrId].getAllData()

    def reqtimeout(self, corrId):
        if corrId in self.subdata:
            del self.subdata[corrId]

    def inreq(self, msg):
        corruuid = msg.correlationId
        dataindex = msg.header['dataindex']

        if dataindex == "pubdata":
            newmsg = d6msg(key=msg.replyTo,
                           replyTo=self.name,
                           correlationId=msg.correlationId,
                           type="rep",
                           dataindex=dataindex,
                           body=dataObject(self.pubdata))
            self.send(newmsg)

        elif dataindex == "subdata":
            newmsg = d6msg(key=msg.replyTo,
                           replyTo=self.name,
                           correlationId=msg.correlationId,
                           type="rep",
                           dataindex=dataindex,
                           body=dataObject(self.subdata))
            self.send(newmsg)

        elif dataindex in self.pubdata:
            reply = d6msg(replyTo=self.name,
                          type="rep",
                          body=self.pubdata[dataindex].get(),
                          srcmsg=msg)
            self.send(reply)

        elif hasattr(self, 'reqhandler'):
            self.pubdata[dataindex] = pubData(dataindex, msg.body)
            self.pubdata[dataindex].requesters[msg.replyTo] = corruuid
            self.reqhandler(msg)

    def inpull(self, msg):
        self.log("received PULL msg: {}".format(str(msg)))
        dataindex = msg.header['dataindex']

        if dataindex in self.pubdata:

            reply = d6msg(replyTo=self.name,
                          type="rep",
                          body=self.pubdata[dataindex].get(),
                          srcmsg=msg)
            self.send(reply)

        else:
            self.pubdata[dataindex] = pubData(dataindex, msg.body)
            self.subhandler(msg)

        self.pubdata[dataindex].addsubscriber(
            msg.replyTo, "pull", msg.correlationId)

    def incmd(self, msg):
        self.log("received CMD msg: {}".format(str(msg)))
        corruuid = msg.correlationId
        dataindex = msg.header['dataindex']

        if corruuid not in self.pubdata:
            self.pubdata[corruuid] = pubData(dataindex, msg.body)
            self.pubdata[corruuid].requesters[msg.replyTo] = corruuid
            self.cmdhandler(msg)

    def insub(self, msg):
        self.log("received SUB msg: {}".format(str(msg)))
        corruuid = msg.correlationId
        dataindex = msg.header['dataindex']
        sender = msg.replyTo

        if corruuid not in self.subscriberCorrelationUuids:

            if dataindex not in self.pubdata:
                self.pubdata[dataindex] = pubData(dataindex, msg.body)
                if hasattr(self, "subhandler"):
                    self.subhandler(msg)

            self.pubdata[dataindex].addsubscriber(sender, "push", corruuid)
            self.subscriberCorrelationUuids.add(corruuid)
            self.push(dataindex, sender, type='sub')

    def inunsub(self, msg):
        self.log("received UNSUB msg: {}".format(str(msg)))
        dataindex = msg.header['dataindex']

        if hasattr(self, 'unsubhandler'):
            if self.unsubhandler(msg):
                if dataindex in self.pubdata:
                    self.pubdata[dataindex].removesubscriber(msg.replyTo)
        else:
            if dataindex in self.pubdata:
                self.pubdata[dataindex].removesubscriber(msg.replyTo)

    def inshut(self, msg):
        """Shut down this data service."""
        self.log("received SHUT msg: {}".format(str(msg)))

        for corruuid in self.subdata:
            self.unsubscribe(corrId=corruuid)

        for thread in self.timerThreads:
            try:
                thread.cancel()
                thread.join()
            except Exception, errmsg:
                self.log("error stopping timer thread: " + errmsg)

        self.running = False

        self.keys = {}
        keydata = {}
        keydata['keys'] = {}
        self.publish("routeKeys", keydata)

    def inpubrep(self, msg):
        self.log("received PUBREP msg: {}".format(str(msg)))
        corruuid = msg.correlationId
        sender = msg.replyTo

        if corruuid in self.subdata:
            callback = self.subdata[corruuid].callback

            if msg.type == 'pub':
                if callback:
                    scrubbed = callback(msg)
                    if scrubbed:
                        self.subdata[corruuid].update(
                            sender, dataObject(scrubbed))

            elif msg.type == 'rep':
                if callback:
                    scrubbed = callback(msg)
                    if scrubbed:
                        self.subdata[corruuid].update(
                            sender, dataObject(scrubbed))

#             if corruuid not in self.scheduuids:
#                 del self.subdata[corruuid]

        else:
            self.unsubscribe(corrId=corruuid)

    def request(
            self,
            key,
            dataindex,
            corrId="",
            callback=None,
            interval=0,
            timer=30,
            args={}):

        msg = d6msg(key=key,
                    replyTo=self.name,
                    correlationId=corrId,
                    type="req",
                    dataindex=dataindex,
                    body=args)

        corruuid = msg.correlationId
        self.subdata[corruuid] = subData(key, dataindex, corruuid, callback)

        if interval:
            self.scheduuids.add(corruuid)
            self.schedule(msg, corruuid, interval, callback)
        else:

            self.send(msg)

            if timer:
                self.timerThreads.append(
                    threading.Timer(
                        timer, self.reqtimeout, [corruuid]).start())

    def reply(self, dataindex, newdata="", delete=True):
        for requester in self.pubdata[dataindex].requesters:

            msg = d6msg(key=requester,
                        replyTo=self.name,
                        correlationId=
                        self.pubdata[dataindex].requesters[requester],
                        type="rep",
                        dataindex=self.pubdata[dataindex].dataindex)

            if newdata:
                msg.body = dataObject(newdata)
            else:
                msg.body = self.pubdata[dataindex].get()
            self.log("REPLY body: " + msg.body)

            self.send(msg)

        if delete:

            del self.pubdata[dataindex]

    def prepush_processor(self, data, dataindex, type=None):
        """Given the DATA to be published, returns the data actually put
        on the wire.  Can be overloaded.
        """
        return data

    def reserved_dataindex(self, dataindex):
        """Returns True if DATAINDEX is one of those reserved by
        deepsix.
        """
        return dataindex in ('routeKeys', 'pubdata', 'subdata')

    def push(self, dataindex, key="", type=None):
        """Send data for DATAINDEX and KEY to subscribers/requesters."""
        self.log("pushing dataindex {} to subscribers {} "
                 "and requesters {} ".format(
                 dataindex,
                 str(self.pubdata[dataindex].subscribers),
                 str(self.pubdata[dataindex].requesters)))
        # bail out if there are no requesters/subscribers
        if (len(self.pubdata[dataindex].requesters) == 0 and
            len(self.pubdata[dataindex].subscribers) == 0):
            self.log("no requesters/subscribers; not sending")
            return

        # give prepush hook chance to morph data
        if self.reserved_dataindex(dataindex):
            data = self.pubdata[dataindex].get()
        else:
            # .get() returns dataObject
            data = self.prepush_processor(self.pubdata[dataindex].get().data,
                                          dataindex,
                                          type=type)
            data = dataObject(data)

        # bail out if prepush hook said there's no data
        if data is None:
            return

        # send to subscribers/requestors
        if self.pubdata[dataindex].subscribers:

            #do = self.pubdata[dataindex].get()
            #logging.info("%s PUSH: %s" % (self.name, do.data))
            if key:
                msg = d6msg(key=key,
                            replyTo=self.name,
                            correlationId=
                            self.pubdata[dataindex]
                            .subscribers[key]['correlationId'],
                            type="pub",
                            dataindex=dataindex,
                            body=data)
                self.send(msg)
            else:
                subscribers = self.pubdata[dataindex].getsubscribers()
                for subscriber in subscribers:

                    if subscribers[subscriber]['type'] == "push":

                        msg = d6msg(key=subscriber,
                                    replyTo=self.name,
                                    correlationId=
                                    subscribers[subscriber]
                                    ['correlationId'],
                                    type="pub",
                                    dataindex=dataindex,
                                    body=data)

                        self.send(msg)

        if self.pubdata[dataindex].requesters:
            if key:
                msg = d6msg(key=key,
                            replyTo=self.name,
                            correlationId=
                            self.pubdata[dataindex].requesters[key],
                            type="rep",
                            dataindex=dataindex,
                            body=self.pubdata[dataindex].get())
                self.send(msg)
                del self.pubdata[dataindex].requesters[key]
            else:
                for requester in self.pubdata[dataindex].requesters.keys():
                    msg = d6msg(key=requester,
                                replyTo=self.name,
                                correlationId=
                                self.pubdata[dataindex]
                                .requesters[requester],
                                type="rep",
                                dataindex=dataindex,
                                body=self.pubdata[dataindex].get())
                    self.send(msg)
                    del self.pubdata[dataindex].requesters[requester]

    def subscribe(
            self,
            key,
            dataindex,
            corrId="",
            callback=None,
            pull=False,
            interval=30,
            args={}):
        """Subscribe to a DATAINDEX for a given KEY."""
        self.log("subscribed to {} with dataindex {}".format(
                 key, dataindex))
        msg = d6msg(key=key,
                    replyTo=self.name,
                    correlationId=corrId,
                    dataindex=dataindex,
                    body=args)
        if pull:
            msg.type = 'pull'
        else:
            msg.type = 'sub'

        corruuid = msg.correlationId

        self.subdata[corruuid] = subData(key, dataindex, corruuid, callback)

        self.scheduuids.add(corruuid)
        self.schedule(msg, corruuid, interval)

        return corruuid

    def unsubscribe(self, key="", dataindex="", corrId=""):
        """Unsubscribe self from DATAINDEX for KEY."""
        self.log("unsubscribed to {} with dataindex {}".format(
                 key, dataindex))
        if corrId:
            if corrId in self.scheduuids:
                self.scheduuids.remove(corrId)
            if corrId in self.subdata:
                key = self.subdata[corrId].key
                dataindex = self.subdata[corrId].dataindex
                del self.subdata[corrId]

            msg = d6msg(key=key,
                        replyTo=self.name,
                        correlationId=corrId,
                        type='unsub',
                        dataindex=dataindex)

            self.send(msg)

        elif key and dataindex:

            for corruuid in self.subdata.keys():

                if key == self.subdata[corruuid].key and \
                        dataindex == self.subdata[corruuid].dataindex:

                    if corruuid in self.scheduuids:
                        self.scheduuids.remove(corruuid)

                    del self.subdata[corruuid]

                    msg = d6msg(key=key,
                                replyTo=self.name,
                                correlationId=corruuid,
                                type='unsub',
                                dataindex=dataindex)
                    self.send(msg)

        return

    def command(
            self,
            key,
            command,
            corrId="",
            callback=None,
            timer=30,
            args={}):

        msg = d6msg(key=key,
                    replyTo=self.name,
                    type="cmd",
                    correlationId=corrId,
                    dataindex=command,
                    body=args)

        corruuid = msg.correlationId

        self.subdata[corruuid] = subData(key, command, corruuid, callback)

        self.send(msg)

        if timer:
            self.timerThreads.append(
                threading.Timer(timer, self.reqtimeout, [corruuid]).start())

    def publish(self, dataindex, newdata, key=''):
        self.log("publishing to dataindex {} with data {}".format(
            str(dataindex), str(newdata)))
        if dataindex not in self.pubdata:
            self.pubdata[dataindex] = pubData(dataindex)

        self.pubdata[dataindex].update(newdata)

        self.push(dataindex, type='pub')

    def receive(self, msg):
        self.log("received msg {}".format(str(msg)))
        if msg.type == 'sub':
            self.insub(msg)
        elif msg.type == 'unsub':
            self.inunsub(msg)
        elif msg.type == 'pub':
            self.inpubrep(msg)
        elif msg.type == 'req':
            self.inreq(msg)
        elif msg.type == 'rep':
            self.inpubrep(msg)
        elif msg.type == 'pull':
            self.inpull(msg)
        elif msg.type == 'shut':
            logging.info("%s received shut from %s" %
                        (self.name, msg.replyTo))
            self.inshut(msg)
        elif msg.type == 'cmd':
            if hasattr(self, 'cmdhandler'):
                self.incmd(msg)
        else:
            assert False, "{} received message of unknown type {}: {}".format(
                self.name, msg.type, str(msg))

    def run(self):
        while self.running:
            # self.log("RUNning")
            if hasattr(self, 'd6run'):
                # self.log("d6running")
                self.d6run()
            # self.log("Checking inbox")
            if not self.inbox.empty():
                # self.log("Found message")
                msg = self.inbox.get()
                self.receive(msg)
                self.inbox.task_done()
            time.sleep(0.1)

    def service_object(self, name):
        if name in self.services:
            return self.services[name]['object']
        else:
            return None

    def subscription_list(self):
        """Return a list version of subscriptions."""
        return [(x.key, x.dataindex) for x in self.subdata.values()]

    def subscriber_list(self):
        """Return a list version of subscribers."""
        result = []
        for pubdata in self.pubdata.values():
            for subscriber in pubdata.subscribers:
                result.append((subscriber, pubdata.dataindex))

    def log(self, msg):
        name = self.name
        # if len(name) >= 8:
        #     shortened = self.name[0:8]
        # name += " " * (8 - len(self.name))
        logging.debug("{}:: {}".format(name, msg))
