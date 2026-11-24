"""pytest suite for Harmony imagenator converter."""
import json
from urllib import request
from typing import Any
from harmony import CapabilitiesRequest, Collection

from tests.conftest import AutotesterRequest
from tests.umm_g_utilities import (
    generate_near_full_variable_subset,
)

def get_filter_variables(
    capabilities: dict[str, Any],
) -> list[str]:
    """Returns list of variables that can be used for filtering

    Removes one variable from the full variable list to avoid
    requesting all variables during subsetting tests.
    """
    vars = []
    variables = capabilities.get('variables')
    # !! set URL based on E
    cmr_url="https://cmr.uat.earthdata.nasa.gov/search/variables.umm_json?page_size=100"
    for variable in variables:
        cmr_url += f"&concept_id={variable['href'].split('/')[-1]}"
    cmr_response = request.urlopen(cmr_url)
    cmr_results = json.loads(cmr_response.read().decode('utf-8'))
    for item in cmr_results['items']:
        umm = item.get('umm', None)
        rurl = umm.get('RelatedURLs', None)
        if rurl:
            for r in rurl:
                if r['URLContentType'] == 'VisualizationURL':
                    vars.append(umm['Definition'])
    return vars

def test_imagenator_l2(failed_tests, harmony_client, service_collection):
    """Run a request against the imagenator_l2 chain and make sure it is successful.

    As a lightweight example, this test will check the Harmony request
    returned a successful status and the output STAC contains only expected
    files. No outputs will be downloaded for further verification to minimise
    overall runtime of the test suite.

    Test fixtures are retrieved from `tests/conftest.py`, which contains
    fixtures common to all Harmony services under test.

    """
    try:
        harmony_request = None

        cap_request = CapabilitiesRequest(
            collection_id=service_collection['concept_id']
        )
        capabilities = harmony_client.submit(cap_request)
        filtering_variables = get_filter_variables(capabilities)
        assert len(filtering_variables) > 0, (
            f"Harmony request failed: {service_collection['concept_id']} has no filtering variables"
        )
        print(f"Using variable {filtering_variables[0]} for collection {service_collection['concept_id']}")
        harmony_request = AutotesterRequest(
            collection=Collection(id=service_collection['concept_id']),
            variables=filtering_variables[0],
            max_results=1,
            format="image/png"
        )

        # Submit the job and get the JSON output once completed
        harmony_job_id = harmony_client.submit(harmony_request)
        result_json = harmony_client.result_json(harmony_job_id)

        # Check the response was successful
        assert result_json['status'] == 'successful', (
            f'Harmony request failed:\n\n{result_json["message"]}'
        )

        # Check the URLs for results are all of the expected type.
        ensure_correct_files_created(result_json['links'])
    except AssertionError as exception:
        # Cache error message and re-raise the AssertionError to fail the test
        url = (
            'NOT_APPLICABLE'
            if harmony_request is None
            else harmony_client.request_as_url(harmony_request)
        )

        failed_tests.append(
            {
                **service_collection,
                'error': str(exception),
                'url': url,
            }
        )
        raise
    except Exception as exception:
        # Catch other exception types and raise as an AssertionError to
        # ensure test test suite is robust against unexpected exceptions.
        # This does not cache the failure, as this should only arise from
        # systematic issues, such as connecting to Harmony, not issues specific
        # to the collection under test.
        raise AssertionError('Unexpected request failure') from exception


def ensure_correct_files_created(harmony_result_json_links: list[dict]):
    """Helper function to check available data links in Harmony results JSON.

    Will ensure:

    * One "data" file is included in the output STAC.
    * Output file has the expected tags in the filename.

    """
    data_links = [link for link in harmony_result_json_links if link['rel'] == 'data']
    assert len(data_links) == 3, 'Should have 3 png output file'

    # All output files should have the correct processing tags.
    processing_tags = ['reformatted']
    assert all(
        all(tag in link['href'] for tag in processing_tags) for link in data_links
    ), 'Not all data links contain all processing tags'
