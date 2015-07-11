from datetime import datetime
import json
import urllib2

import mock
import pytest

from django.core.urlresolvers import reverse
from django import http

from .. import views
from .. import models


# Add this mark so that we are not loading all the urls for
# the entire project when using reverse.
pytestmark = pytest.mark.urls('coda_mdstore.urls')


@pytest.fixture
def patch_site(monkeypatch):
    Site = mock.Mock()
    Site.objects.get_current().name = 'example.com'
    monkeypatch.setattr('coda_mdstore.views.Site', Site)
    return Site


@pytest.mark.usefixtures('patch_site')
class TestIndexView:

    # @pytest.fixture(autouse=True)
    def setup_method(self, method):
        """
        Setup the tests for ..views.index by mocking the database
        models. This will be automatically provided to all the
        test methods.
        """
        self.bag_patcher = mock.patch('coda_mdstore.views.Bag')
        self.queue_entry_patcher = mock.patch('coda_mdstore.views.QueueEntry')
        self.validate_patcher = mock.patch('coda_mdstore.views.Validate')
        self.event_patcher = mock.patch('coda_mdstore.views.Event')

        self.mock_bag = self.bag_patcher.start()
        self.mock_queue_entry = self.queue_entry_patcher.start()
        self.mock_validate = self.validate_patcher.start()
        self.mock_event = self.event_patcher.start()

        self.mock_bag.objects.all().aggregate.return_value = {'files__sum': 1}
        self.mock_queue_entry.objects.count.return_value = 10
        self.mock_validate.objects.count.return_value = 10
        self.mock_event.objects.count.return_value = 10

    def teardown_method(self, method):
        self.bag_patcher.stop()
        self.queue_entry_patcher.stop()
        self.validate_patcher.stop()
        self.event_patcher.stop()

    def test_returns_status_code_200(self, rf):
        request = rf.get('/')
        response = views.index(request)
        assert response.status_code == 200

    @pytest.mark.parametrize('key', [
        'site_title',
        'totals',
        'queue_total',
        'validation_total',
        'event_total',
        'maintenance_message'
    ])
    def test_context_has_key(self, key, client):
        response = client.get(reverse('coda_mdstore.views.index'))
        assert key in response.context[-1]

    def test_renders_correct_template(self, client):
        response = client.get(reverse('coda_mdstore.views.index'))
        assert response.template[0].name == 'mdstore/index.html'

    def test_totals_files__sum_key_is_none(self, client, monkeypatch):
        """
        Check that the `files__sum` key is set 0 if the db returns
        None.
        """
        # Re-patch the Bag entity to modify the return value from the
        # database query.
        self.mock_bag.objects.all().aggregate.return_value = {
            'files__sum': None
        }

        response = client.get(reverse('coda_mdstore.views.index'))
        assert response.context[-1]['totals']['files__sum'] == 0


@pytest.mark.usefixtures('patch_site')
class TestAboutView:

    def test_renders_correct_template(self, client):
        response = client.get(reverse('coda_mdstore.views.about'))
        assert response.template[0].name == 'mdstore/about.html'


@pytest.mark.usefixtures('patch_site')
class TestStatsView:

    @mock.patch('coda_mdstore.views.Bag')
    def test_no_bags_available(self, mock_bag, client):
        mock_bag.objects.count.return_value = 0
        response = client.get(reverse('coda_mdstore.views.stats'))

        assert response.status_code == 200

        assert response.context[-1]['totals'] == 0
        assert response.context[-1]['monthly_bags'] == []
        assert response.context[-1]['monthly_files'] == []
        assert response.context[-1]['monthly_running_bag_total'] == []
        assert response.context[-1]['monthly_running_file_total'] == []

    @pytest.mark.xfail
    def test_with_bags(self):
        assert 0


class TestJSONStatsView:

    @mock.patch('coda_mdstore.views.Bag')
    @mock.patch('coda_mdstore.views.Node')
    def test_no_bags_or_nodes(self, mock_node, mock_bag, client):
        mock_node.objects.aggregate.return_value = {'node_capacity__sum': 0}
        mock_bag.objects.aggregate.return_value = {
            'bagging_date__max': None,
            'pk__count': 0,
            'size__sum': 0,
            'files__sum': 0
        }

        response = client.get(reverse('coda_mdstore.views.json_stats'))
        payload = json.loads(response.content)

        assert len(payload) == 5
        assert payload['bags'] == 0
        assert payload['capacity'] == 0
        assert payload['capacity_used'] == 0
        assert payload['files'] == 0
        assert payload['updated'] == ''

    @mock.patch('coda_mdstore.views.Bag')
    @mock.patch('coda_mdstore.views.Node')
    def test_with_bags_and_nodes(self, mock_node, mock_bag, client):
        mock_node.objects.aggregate.return_value = {
            'node_capacity__sum': 1000000
        }
        mock_bag.objects.aggregate.return_value = {
            'bagging_date__max': datetime(2015, 01, 01),
            'pk__count': 50,
            'size__sum': 100000,
            'files__sum': 1000,
        }

        response = client.get(reverse('coda_mdstore.views.json_stats'))
        payload = json.loads(response.content)

        assert len(payload) == 5
        assert payload['bags'] == 50
        assert payload['capacity'] == 1000000
        assert payload['capacity_used'] == 100000
        assert payload['files'] == 1000
        assert payload['updated'] == '2015-01-01'


@pytest.mark.usefixtures('patch_site')
class TestAllBagsView:

    @pytest.fixture(autouse=True)
    def mock_pe(self, monkeypatch):
        """Patches the paginate_entries with a Mock object."""
        mock_pe = mock.Mock()
        monkeypatch.setattr(
            'coda_mdstore.views.paginate_entries', mock_pe)

        return mock_pe

    def test_renders_correct_template(self, client):
        response = client.get(reverse('coda_mdstore.views.all_bags'))
        assert response.template[0].name == 'mdstore/bag_search_results.html'

    def test_uses_paginated_entries(self, mock_pe, client, monkeypatch):
        mock_pe.return_value = 'fake data'

        response = client.get(reverse('coda_mdstore.views.all_bags'))
        assert mock_pe.call_count == 1
        assert response.context[-1]['entries'] == 'fake data'

    @pytest.mark.parametrize('key', [
        'site_title',
        'entries',
        'maintenance_message'
    ])
    def test_context_has_key(self, key, client):
        response = client.get(reverse('coda_mdstore.views.all_bags'))
        assert key in response.context[-1]


class TestRobotsView:

    def test_user_agent_is_all(self, rf):
        request = rf.get('/')
        response = views.shooRobot(request)
        assert 'User-agent: *' in response.content

    def test_disallow(self, rf):
        request = rf.get('/')
        response = views.shooRobot(request)
        assert 'Disallow: /' in response.content


@pytest.mark.usefixtures('patch_site')
class TestBagHTMLView:

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        Bag = mock.Mock()
        monkeypatch.setattr('coda_mdstore.views.get_object_or_404', Bag)

        self.payload_oxum = mock.MagicMock()
        self.payload_oxum.field_name = 'Payload-Oxum'

        self.bagging_date = mock.MagicMock()
        self.bagging_date.field_name = 'Bagging-Date'
        self.bagging_date.field_body = '2015-01-01'

        Bag_Info = mock.Mock()
        Bag_Info.objects.filter.return_value = [
            self.bagging_date,
            self.payload_oxum
        ]
        monkeypatch.setattr('coda_mdstore.views.Bag_Info', Bag_Info)

    @pytest.mark.xfail(reason='View cannot handle bag without a member '
                              'Payload-Oxum Bag_Info')
    def test_bag_info_does_not_have_payload_oxum(self, rf):
        self.payload_oxum.field_name = ''
        response = views.bagHTML(rf.get('/'), 'fake-identifier')

        assert response.status_code in (200, 404)

    @pytest.mark.xfail(reason='View cannot handle bag without a member '
                              'Bagging-Date Bag_Info')
    def test_bag_info_does_not_have_bagging_date(self, rf):
        self.bagging_date.field_name = ''
        response = views.bagHTML(rf.get('/'), 'fake-identifier')

        assert response.status_code in (200, 404)

    def test_catches_urlerror(self, client, monkeypatch):
        urlopen = mock.Mock(side_effect=urllib2.URLError('Fake Exception'))
        monkeypatch.setattr('coda_mdstore.views.urllib2.urlopen', urlopen)

        response = client.get(
            reverse('coda_mdstore.views.bagHTML', args=['fake-identifier']))

        assert urlopen.call_count == 1
        assert response.context[-1]['json_events'] == {}

    def test_renders_correct_template(self, client):
        response = client.get(
            reverse('coda_mdstore.views.bagHTML', args=['fake-identifier']))

        assert response.template[0].name == 'mdstore/bag_info.html'

    @pytest.mark.parametrize('key', [
        'site_title',
        'json_events',
        'payload_oxum_file_count',
        'payload_oxum_size',
        'bag_date',
        'bag',
        'bag_info',
        'maintenance_message'
    ])
    def test_context_has_key(self, key, client):
        response = client.get(
            reverse('coda_mdstore.views.bagHTML', args=['fakeid']))

        assert key in response.context[-1]


class TestBagProxyView:

    @pytest.fixture(autouse=True)
    def setup_method(self, monkeypatch):
        Bag = mock.Mock()
        Bag.objects.get.return_value = Bag
        monkeypatch.setattr('coda_mdstore.views.Bag', Bag)

        # The mocked value that getFileHandle will return.
        fileHandle = mock.Mock()
        fileHandle.info().getheader.side_effect = ['text/plain', '255']
        monkeypatch.setattr(
            'coda_mdstore.views.getFileHandle',
            mock.Mock(return_value=fileHandle))

    def test_returns_status_code_200(self, rf):
        request = rf.get('/')
        response = views.bagProxy(request, 'fake-identifier', '/foo/bar')
        assert response.status_code == 200

    def test_response_has_correct_headers(self, rf):
        request = rf.get('/')
        response = views.bagProxy(request, 'fake-identifier', '/foo/bar')
        assert response['Content-Length'] == '255'
        assert response['Content-Type'] == 'text/plain'

    @mock.patch('coda_mdstore.views.Bag')
    def test_raises_not_found_when_object_not_found(self, mock_bag, rf):
        mock_bag.DoesNotExist = models.Bag.DoesNotExist
        mock_bag.objects.get.side_effect = models.Bag.DoesNotExist

        request = rf.get('/')
        response = views.bagProxy(request, 'fake-identifier', '/foo/bar')

        assert isinstance(response, http.HttpResponseNotFound)
        assert response.content == "There is no bag with id 'fake-identifier'."

    def test_raises_http404_when_file_handle_is_false(self, rf, monkeypatch):
        monkeypatch.setattr(
            'coda_mdstore.views.getFileHandle', mock.Mock(return_value=False))
        request = rf.get('/')

        with pytest.raises(http.Http404):
            views.bagProxy(request, 'fake-identifier', '/foo/bar')

    @pytest.mark.xfail
    def test_bag_proxy_catches_exception_raised_by_getFileHandler(self):
        assert 0


class TestBagURLListView:

    @pytest.mark.xfail(msg='Response content does not match other responses.')
    @mock.patch('coda_mdstore.views.Bag')
    def test_raises_not_found_when_object_not_found(self, mock_bag, rf):
        mock_bag.DoesNotExist = models.Bag.DoesNotExist
        mock_bag.objects.get.side_effect = models.Bag.DoesNotExist

        request = rf.get('/')
        response = views.bagURLList(request, 'fake-identifier')

        assert isinstance(response, http.HttpResponseNotFound)
        assert response.content == "There is no bag with id 'fake-identifier'."

    @pytest.mark.xfail
    def test_raises_http404_file_handle_is_falsy(self):
        assert 0

    @pytest.mark.xfail
    def test_output_text(self):
        assert 0

    @pytest.mark.xfail
    def test_top_files_block(self):
        # TODO: rename once implemented.
        assert 0

    @pytest.mark.xfail
    def test_path_is_not_unicode_safe(self):
        assert 0

    @pytest.mark.xfail
    def test_returns_status_code_200(self):
        assert 0


class TestBagURLListScrapeView:

    @mock.patch('coda_mdstore.views.Bag')
    def test_raises_not_found_when_object_not_found(self, mock_bag, rf):
        mock_bag.DoesNotExist = models.Bag.DoesNotExist
        mock_bag.objects.get.side_effect = models.Bag.DoesNotExist

        request = rf.get('/')
        response = views.bagURLListScrape(request, 'fake-identifier')

        assert isinstance(response, http.HttpResponseNotFound)
        assert response.content == "There is no bag with id 'fake-identifier'."

    @pytest.mark.xfail(msg='pairtreeCandidateList is not available in scope.')
    @mock.patch('coda_mdstore.views.Bag')
    @mock.patch('coda_mdstore.views.getFileHandle')
    def test_raises_http404_file_handle_is_falsy(self, mock_gfh, mock_bag, rf):
        mock_gfh.return_value = False
        request = rf.get('/')

        with pytest.raises(http.Http404):
            views.bagURLListScrape(request, 'fake-identifier')

    @pytest.mark.xfail(msg='pairtreeCandidateList is not available in scope.')
    def test_response_content(self):
        assert 0


class TestBagFullTextSearchATOMView:

    @pytest.mark.xfail()
    def test_smoke(self):
        assert 0


class TestBagFullTextSearchView:

    @pytest.mark.xfail()
    def test_smoke(self):
        assert 0


class TestShowNodeStatusView:

    @pytest.mark.xfail()
    def test_smoke(self):
        assert 0


class TestAppNode:

    @pytest.mark.xfail()
    def test_smoke(self):
        assert 0


class TestAppBag:

    @pytest.mark.xfail()
    def test_smoke(self):
        assert 0


class IntegrationTests:
    pass
