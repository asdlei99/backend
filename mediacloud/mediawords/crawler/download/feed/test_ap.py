"""Unit tests for mediawords.crawler.download.feed.ap"""

import json
from unittest import TestCase
from bs4 import BeautifulSoup
import ap
import time
import os

import httpretty

import mediawords.crawler.download.feed.ap as ap
from mediawords.test.test_database import TestDatabaseWithSchemaTestCase
import mediawords.util.config

from mediawords.util.log import create_logger
log = create_logger(__name__)

def test_ap_config_section() -> None:
    """Test config section is present for AP Fetcher"""
    config = mediawords.util.config.get_config()
    assert 'associated_press' in config, "associated_press section present in mediawords.yml"
    assert 'apikey' in config['associated_press'], "apikey keyword present in associated_press section of mediawords.yml"


def test_convert_publishdate_to_epoch() -> None:
    """Test publishdate time conversion to epoch (from UTC datetime) is correct"""
    assert ap._convert_publishdate_to_epoch('2019-01-01T12:00:00Z') == 1546344000


def test_extract_url_parameters() -> None:
    """Test parameter extraction from url"""
    url = 'https://www.google.com/page?a=5&b=abc'
    assert ap._extract_url_parameters(url) == {'a': '5', 'b': 'abc'}

def setup_mock_api(test: TestCase) -> None:
    """Setup mock associate press api using httpretty."""
    base_dir = os.path.dirname(os.path.realpath(__file__))
    fixture_data_dir = '{base_dir}/ap_test_fixtures/'.format(base_dir=base_dir)
    test._api = ap.AssociatedPressAPI()
    ap._api = test._api
    MOCK_RESPONSE_HEADERS = {'Content-Type': 'application/json; charset=utf-8',
                             'x-mediaapi-Q-name': 'feed',
                             'x-mediaapi-Q-secondsLeft': '30',
                             'x-mediaapi-Q-used': '1/100'}

    fixture_feed_data = open(fixture_data_dir + "test_ap_fixture_feed_data","r").read()
    fixture_search_data = open(fixture_data_dir + "test_ap_fixture_search_data","r").read()
    fixture_test_data = open(fixture_data_dir + "test_ap_fixture_test_data","r").read()
    test.fixture_test_data = json.loads(fixture_test_data)
    test.fixture_data_stories = json.loads(fixture_feed_data)['data']['items']
    fixture_content_data = json.loads(open(fixture_data_dir + "test_ap_fixture_content_data","r").read())
    test.required_fields = set(['guid','url','publish_date','title','description','text','content'])
    test.present_guids = set()

    for item in test.fixture_data_stories:
        story = item['item']
        guid = story['altids']['itemid']
        test.present_guids.add(guid)
        version = story['version']
        mock_content_url = "https://api.ap.org/media/v/content/{guid}".format(guid=guid)
        mock_nitf_url = "https://api.ap.org/media/v/content/{guid}.{version}/download".format(guid=guid,version=version)
        content_mock_body = json.dumps(fixture_content_data[guid])
        nitf_mock_body = open(fixture_data_dir + "test_ap_fixture_{guid}.nitf".format(guid=guid),"r").read().rstrip()

        # Register mock content responses
        httpretty.register_uri(httpretty.GET, mock_content_url, adding_headers=MOCK_RESPONSE_HEADERS, body = content_mock_body)

        # Register mock nitf responses
        httpretty.register_uri(httpretty.GET, mock_nitf_url, adding_headers=MOCK_RESPONSE_HEADERS, body = nitf_mock_body)

    httpretty.enable()


def teardown_mock_api(test: TestCase) -> None:
    """Tear down Associarted Press mock api."""
    httpretty.disable()
    httpretty.reset()


class TestAPFetcher(TestCase):
    """Test Class for AP Story Fetcher"""

    def setUp(self):
        """Setup Method"""
        setup_mock_api(self)

    def tearDown(self) -> None:
        """Teardown method"""
        teardown_mock_api(self)


    def test_fetch_nitf_rendition(self) -> None:
        """Test fetching of nitf content and that it is valid XML and correct size"""
        story_item = self.fixture_data_stories[0]['item']
        nitf_content = ap._fetch_nitf_rendition(story_item)
        actual_nitf_content_length = 2854
        soup = BeautifulSoup(nitf_content,features="html.parser")
        body_content = soup.find('body.content').text
        assert len(body_content) == actual_nitf_content_length

    def test_process_stories(self) -> None:
        """Test that all stories are processed and all required fields are present"""
        stories = ap._process_stories(self.fixture_data_stories)

        # Test that all stories were processed successfully
        for guid in self.present_guids:
            assert guid in stories

        # Test that all required fields were returned for each story
        for guid, story in stories.items():
            for key in self.required_fields:
                assert key in story

        # Test that each field has the correctly parsed data
        for guid, story in stories.items():
            for key in self.required_fields:
                assert self.fixture_test_data[guid][key] == story[key]

class TestAPFetcherDB(TestDatabaseWithSchemaTestCase):
    """Test Class with AP mock api and database."""

    def setUp(self) -> None:
        super().setUp()
        setup_mock_api(self)

    def tearDown(self) -> None:
        super().tearDown()
        teardown_mock_api(self)

    def test_get_and_add_new_stories(self) -> None:
        """Test get_and_ad_new_stories()."""
        db = self.db()

        ap.get_and_add_new_stories(db)

        stories = db.query("select * from stories").hashes()

        assert len(stories) == len(self.fixture_data_stories) + 1

