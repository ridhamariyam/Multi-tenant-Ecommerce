"""A customer's delivery addresses."""

from __future__ import annotations

from tests.conftest import headers_for
from tests.orders.conftest import ADDRESSES, CUSTOMERS, address_payload


async def test_an_address_is_saved_and_read_back(client, customer_auth):
    response = await client.post(
        ADDRESSES, json=address_payload(), headers=customer_auth
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["city"] == "Bengaluru"
    assert body["postal_code"] == "560025"


async def test_an_indian_postal_code_must_be_six_digits(client, customer_auth):
    response = await client.post(
        ADDRESSES,
        json=address_payload(postal_code="682001738233"),
        headers=customer_auth,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "postal_code"


async def test_a_postal_code_outside_india_is_not_held_to_the_pin_format(
    client, customer_auth
):
    response = await client.post(
        ADDRESSES,
        json=address_payload(country="United Kingdom", postal_code="SW1A 1AA"),
        headers=customer_auth,
    )

    assert response.status_code == 201


async def test_the_first_address_becomes_the_default(client, make_user, tenant):
    user = await make_user(tenant=tenant, phone="+919822221001")
    headers = headers_for(user)

    first = await client.post(ADDRESSES, json=address_payload(), headers=headers)
    second = await client.post(
        ADDRESSES, json=address_payload(city="Kochi"), headers=headers
    )

    assert first.json()["data"]["is_default"] is True
    assert second.json()["data"]["is_default"] is False


async def test_making_one_default_demotes_the_previous_one(
    client, make_user, tenant
):
    user = await make_user(tenant=tenant, phone="+919822221002")
    headers = headers_for(user)

    first = await client.post(ADDRESSES, json=address_payload(), headers=headers)
    second = await client.post(
        ADDRESSES, json=address_payload(city="Kochi"), headers=headers
    )

    promoted = await client.patch(
        f"{ADDRESSES}/{second.json()['data']['id']}",
        json={"is_default": True},
        headers=headers,
    )
    assert promoted.status_code == 200, promoted.text

    listing = await client.get(ADDRESSES, headers=headers)
    defaults = [a["id"] for a in listing.json()["data"] if a["is_default"]]
    assert defaults == [second.json()["data"]["id"]]
    assert first.json()["data"]["id"] not in defaults


async def test_a_phone_number_is_normalised(client, customer_auth):
    response = await client.post(
        ADDRESSES, json=address_payload(phone="9876500009"), headers=customer_auth
    )

    assert response.json()["data"]["phone"] == "+919876500009"


async def test_a_blank_name_is_refused(client, customer_auth):
    response = await client.post(
        ADDRESSES, json=address_payload(full_name="   "), headers=customer_auth
    )

    assert response.status_code == 422


async def test_an_address_can_be_updated(client, customer_auth, save_address):
    saved = await save_address(customer_auth)

    response = await client.patch(
        f"{ADDRESSES}/{saved['id']}", json={"city": "Kochi"}, headers=customer_auth
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["city"] == "Kochi"


async def test_an_address_can_be_deleted(client, customer_auth, save_address):
    saved = await save_address(customer_auth)

    deleted = await client.delete(f"{ADDRESSES}/{saved['id']}", headers=customer_auth)
    assert deleted.status_code == 204

    gone = await client.get(f"{ADDRESSES}/{saved['id']}", headers=customer_auth)
    assert gone.status_code == 404


async def test_a_listing_only_shows_your_own_addresses(
    client, customer_auth, save_address, make_user, tenant
):
    await save_address(customer_auth)

    intruder = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])
    response = await client.get(ADDRESSES, headers=headers_for(intruder))

    assert response.json()["data"] == []


async def test_another_customers_address_is_not_found(
    client, customer_auth, save_address, make_user, tenant
):
    saved = await save_address(customer_auth)

    intruder = await make_user(tenant=tenant, phone="+919822221003")
    response = await client.get(
        f"{ADDRESSES}/{saved['id']}", headers=headers_for(intruder)
    )

    assert response.status_code == 404


async def test_an_anonymous_caller_is_rejected(client, tenant):
    response = await client.get(ADDRESSES)

    assert response.status_code == 401


async def test_staff_may_not_manage_customer_addresses(client, staff_headers, tenant):
    response = await client.get(ADDRESSES, headers=staff_headers)

    assert response.status_code == 403
