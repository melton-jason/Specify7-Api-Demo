import json
import requests
import re
import logging

from functools import wraps
from typing import Literal, Optional, Dict, Tuple, Union, Any, List

logger = logging.getLogger(__name__)


class InvalidMethod(Exception):
    ...


class VersionMismatch(Exception):
    ...


class InvalidCredentials(Exception):
    ...


class NoPermission(Exception):
    ...


REQUEST_METHOD = Literal['GET', 'PUT', 'POST', 'DELETE']
HIEARCHY = Literal['Collection', 'Discipline', 'Division', 'Institution']


FIELD_VALUE = Union[int, str, bool, None,
                    List['SERIALIZED_RECORD'], 'SERIALIZED_RECORD']
SERIALIZED_RECORD = Dict[str, FIELD_VALUE]

# Regex matching api uris for extracting the model name and id number.
URI_RE = re.compile(r'^\/api\/specify\/(\w+)\/($|(\d+))')


def parse_uri(uri: str) -> Tuple[str, str]:
    """Return the model name and id from a resource URI."""
    match = URI_RE.match(uri)
    assert match is not None, f"Bad URI: {uri}"
    groups = match.groups()
    table, resource_id = groups[0], groups[2]
    return table, resource_id


def extract_id_from_uri(uri: str):
    """From a given uri to a resource, extract the id 
    """
    _, resource_id = parse_uri(uri)
    return int(resource_id)


def construct_api_link(table: str, id: int):
    """Given a <table> and <id>, construct the resource_uri for the record
    """
    return f"/api/specify/{table.lower()}/{id}/"


def ensure_login(func):
    """Decorator which ensures a function which accepts a Session as the first
    parameter is logged in before the function is called 
    """
    @wraps(func)
    def wrapped(session: "Session", *args: Tuple, **kwargs: Dict[str, Any]):
        if session.specifyuser is None:
            raise Exception("Must be logged in")
        return func(session, *args, **kwargs)

    return wrapped


class Session:
    def __init__(self, *,  domain="http://localhost", port=None) -> None:
        self.domain = domain
        self.port = port
        self.session = requests.Session()
        self._collections: Dict[str, int] = dict()
        self._hierarchy: Dict[HIEARCHY, int] = {
            "Collection": -1,
            "Discipline": -1,
            "Division": -1,
            "Institution": -1
        }
        self.specifyuser: Optional[SERIALIZED_RECORD] = None
        self._init_session()

    def send_request(self, method: REQUEST_METHOD, endpoint: str, *args, **kwargs) -> requests.Response:
        """Sends a request with method <method> to the <endpoint>. 
        Specifically, gets the corresponding method from `requests` and 
        supplies it with <args> and <kwargs>. 

        The following are equivalent (assuming the domain is `http://localhost`):
        ```
        r = session.send_request('POST', '/api/specify/agent/', json={"lastname": "Doe"}) 
        r = requests.post('http://localhost/api/specify/agent/', json={"lastname": "Doe"})
        ```
        """
        full_url = self.domain + endpoint
        request_function = getattr(self.session, method.lower(), None)
        if request_function is None or not callable(request_function):
            raise InvalidMethod(method)

        logger.info(f"{method} | {full_url} {
                    '| ' + str(kwargs) if len(kwargs) > 0 else ''}")

        return request_function(full_url, *args, **kwargs)

    def login(self, username: str, password: str, collection_id: int):
        """Login as Specifyuser <username> with password <password> to 
        collection <collection_id> 
        """
        r = self.send_request('PUT', '/context/login/', json={
                              "username": username, "password": password, "collection": collection_id})

        if r.status_code == 403:
            raise InvalidCredentials(r.content)
        if r.status_code == 400:
            raise Exception(r.content)
        self.specifyuser = json.loads(self.send_request(
            'GET', '/context/user.json').content)
        self.session.headers.update({"X-CSRFToken": r.cookies["csrftoken"]})
        self._update_hierarchy(collection_id)

    def get_domain_id(self, scope: HIEARCHY) -> Optional[int]:
        return self._hierarchy.get(scope, None)

    @ensure_login
    def fetch_resource(self, table: str, resource_id: int) -> SERIALIZED_RECORD:
        """Returns the serialzied record from <table> with id of resource_id

        Literal field values are directly mapped from `{field : value}` in the
        returned response. 
        As in, 
        ```py
        {
        "text1": "someStringValue",
        "yesno1": True,
        "number1": 10,
        "remarks": None
        }
        ```
        ---
        Independent -to-one relationships are returned via the resource_uri
        of the related record or `None` if the relationship is none
        For example, the following record is not associated with any accession,
        but is related to the collection with an id of 4:
        ```py
        {
        "accession": None,
        "collection": "/api/specify/collection/4/"
        }
        ```
        ---
        Dependent resources are returned by either None, serialized inline 
        (in the case of a -to-one relationship), or each serialized in an array 
        (in the case of a -to-many relationship)

        For example: 
        ```py
        {
            "collectionobjectattribute" : {
                "id": 234,
                ... # rest of collectionobjectattribute
            },
            "preparations": [
            {
                "id": 1,
                ... # rest of prep 1
            },
            {
                "id": 2,
                ... # rest of prep 2
            }
            ]
        }
        ```
        """
        r = self.send_request(
            'GET', f'/api/specify/{table.lower()}/{resource_id}/')

        if r.status_code == 403:
            raise NoPermission(r.content)
        elif r.status_code != 200:
            raise Exception(r.status_code, r.content)

        return json.loads(r.content)

    @ensure_login
    def fetch_collection(self, url: str) -> Tuple[SERIALIZED_RECORD]:
        """Returns the array of serialized objects returned from fetching 
        the url
        """
        r = self.send_request('GET', url)

        if r.status_code == 403:
            raise NoPermission(r.content)
        elif r.status_code != 200:
            raise Exception(r.status_code, r.content)

        return tuple(json.loads(r.content)['objects'])

    @ensure_login
    def create_resource(self, table: str, data: SERIALIZED_RECORD) -> SERIALIZED_RECORD:
        """Creates a <table> resource with the data provided in <data>.

        Independent relationships can be established via the resource_uri of
        the other resource. As in:
        ```py
        # The following CollectionObject will be in the Collection with an id 
        # of 4
        session.create_resource("collectionobject", {
            ... # Other CO data
            "collection": "/api/specify/collection/4/"
        })
        ```
        ---
        Dependent resources of <table> can be created at the same time as 
        the record of <table>, as in the following examples:

        ```py
        session.create_resource('collectionobject', {
            ... # CO data
            "collectionobjectattribute": {
                ... # serialzied collectionobjectattribute
            }
        })
        session.create_resource('collectionobject', {
            ... # CO data
            "preparations": [
                {
                    ... # new prep1
                },
                {
                    ... # new prep2
                }
            ]
        })
        ```
        """
        r = self.send_request(
            'POST', f'/api/specify/{table.lower()}/', json=data)

        if r.status_code == 403:
            raise NoPermission(r.content)
        elif r.status_code != 201:
            raise Exception(r.status_code, r.content)

        return json.loads(r.content)

    @ensure_login
    def update_resource(self, table: str, resource_id: int, updated: SERIALIZED_RECORD) -> SERIALIZED_RECORD:
        """Updates the <table> resource identified with <resource_id> with the 
        keys/values in `updated` where the keys are field names 
        mapping to values.
        All other fields/relationships not specified in 
        `updated` do not get changed. 
        ---
        Dependent records of <table> can be directly modified and created 
        For example: 
        ```py
        session.update_resource('collectionobject', 1, {
            "collectionobjectattribute": {
                ... # serialzied collectionobjectattribute
            }
        })
        session.update_resource('collectionobject', 1, {
            "preparations": [
                {
                    ... #prep1
                },
                {
                    ... #prep2
                }
            ]
        })
        ```
        """
        current_resource = self.fetch_resource(table, resource_id)
        current_resource.update(updated)
        resp = self.send_request(
            'PUT', construct_api_link(table, resource_id), json=current_resource)
        if resp.status_code == 400:
            raise Exception(
                "Resource version needs to be included", resp.content)
        elif resp.status_code == 409:
            raise VersionMismatch(resp.content)
        elif resp.status_code != 200:
            raise Exception(resp.status_code, resp.content)

        return json.loads(resp.content)

    @ensure_login
    def logout(self):
        self.send_request('PUT', '/context/login/',
                          json={"username": None, "password": None, "collection": self.get_domain_id('Collection')})
        self.specifyuser = None

    def get_collection_id(self, collection_name: str) -> Optional[int]:
        """Returns the collection id of the given `collection_name`. 
        Returns None if no Collection exists with the name
        """
        return self._collections.get(collection_name, None)

    def get_collections(self) -> Dict[str, int]:
        """Returns a dictionary of available collections of the form
        {"collection_name": collectionId}
        """
        return self._collections

    def _init_session(self) -> None:
        r = self.send_request('GET', "/context/login/")
        content = json.loads(r.content)
        self.session.headers.update({"X-CSRFToken": r.cookies["csrftoken"]})
        self._collections = {collection: collection_id for (
            collection, collection_id) in content['collections'].items()}

    def _update_hierarchy(self, collection_id):
        dis_id = extract_id_from_uri(self.fetch_resource(
            'collection', collection_id)['discipline'])
        div_id = extract_id_from_uri(
            self.fetch_resource('discipline', dis_id)['division'])
        inst_id = extract_id_from_uri(
            self.fetch_resource('division', div_id)['institution'])

        self._hierarchy['Institution'] = inst_id
        self._hierarchy['Division'] = div_id
        self._hierarchy['Discipline'] = dis_id
        self._hierarchy['Collection'] = collection_id
