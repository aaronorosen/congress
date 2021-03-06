# Copyright (c) 2014 VMware, Inc. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

from congress.dse import deepsix
from congress.openstack.common import log as logging
from congress.policy import compile


def d6service(name, keys, inbox, datapath, args):
    return RowModel(name, keys, inbox=inbox, dataPath=datapath, **args)


LOG = logging.getLogger(__name__)


class RowModel(deepsix.deepSix):
    """Model for handling API requests about Tables."""
    def __init__(self, name, keys, inbox=None, dataPath=None,
                 policy_engine=None):
        super(RowModel, self).__init__(name, keys, inbox=inbox,
                                       dataPath=dataPath)
        self.engine = policy_engine

    # TODO(thinrichs): No rows have IDs right now.  Maybe eventually
    #   could make ID the hash of the row, but then might as well
    #   just make the ID a string repr of the row.  No use case
    #   for it as of now since all rows are read-only.
    # def get_item(self, id_, context=None):
    #     """Retrieve item with id id_ from model.

    #     Args:
    #         id_: The ID of the item to retrieve
    #         context: Key-values providing frame of reference of request

    #     Returns:
    #          The matching item or None if item with id_ does not exist.
    #     """

    def get_items(self, context=None):
        """Get items in model.

        Args:
            context: Key-values providing frame of reference of request

        Returns: A tuple (id, item) for all items in model.
        """
        LOG.info("get_items(context=%s)", str(context))
        if context['ds_id'] in self.engine.theory:
            tablename = context['table_id']
            arity = self.engine.theory[context['ds_id']].get_arity(tablename)
            if arity is None:
                return []
            args = ["x" + str(i) for i in xrange(0, arity)]
            query = compile.parse1(tablename + "(" + ",".join(args) + ")")
            LOG.info("query: " + str(query))
            literals = self.engine.theory[context['ds_id']].select(query)
        else:
            tablename = context['ds_id'] + ":" + context['table_id']
            arity = self.engine.theory[
                self.engine.theory.DATABASE].get_arity(tablename)
            if arity is None:
                return []
            args = ["x" + str(i) for i in xrange(0, arity)]
            query = compile.parse1(tablename + "(" + ",".join(args) + ")")
            LOG.info("query: " + str(query))
            literals = self.engine.theory[
                self.engine.theory.DATABASE].select(query)

        result = []
        for lit in literals:
            d = {}
            d['data'] = [arg.name for arg in lit.arguments]
            # tuples don't have IDs for now.  Could hash them I suppose.
            #  But if you're trying to use an ID you're doing
            #  something wrong.
            result.append((None, d))
        return result

    # TODO(thinrichs): It makes sense to sometimes allow users to create
    #  a new row for internal data sources.  But since we don't have
    #  those yet all tuples are read-only from the API.

    # def add_item(self, item, id_=None, context=None):
    #     """Add item to model.

    #     Args:
    #         item: The item to add to the model
    #         id_: The ID of the item, or None if an ID should be generated
    #         context: Key-values providing frame of reference of request

    #     Returns:
    #          Tuple of (ID, newly_created_item)

    #     Raises:
    #         KeyError: ID already exists.
    #     """


    # TODO(thinrichs): once we have internal data sources,
    #   add the ability to update a row.  (Or maybe not and implement
    #   via add+delete.)
    # def update_item(self, id_, item, context=None):
    #     """Update item with id_ with new data.

    #     Args:
    #         id_: The ID of the item to be updated
    #         item: The new item
    #         context: Key-values providing frame of reference of request

    #     Returns:
    #          The updated item.

    #     Raises:
    #         KeyError: Item with specified id_ not present.
    #     """
    #     # currently a noop since the owner_id cannot be changed
    #     if id_ not in self.items:
    #         raise KeyError("Cannot update item with ID '%s': "
    #                        "ID does not exist")
    #     return item

    # TODO(thinrichs): once we can create, we should be able to delete
    # def delete_item(self, id_, context=None):
        # """Remove item from model.

        # Args:
        #     id_: The ID of the item to be removed
        #     context: Key-values providing frame of reference of request

        # Returns:
        #      The removed item.

        # Raises:
        #     KeyError: Item with specified id_ not present.
        # """
