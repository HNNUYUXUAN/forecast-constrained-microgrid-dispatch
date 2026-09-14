import numpy as np
import pytest
from c_grid.src.settlement import settle_purchase, storage_residual


def test_settlement_keeps_original_commitment():
    got = settle_purchase([2,2,2],[10,10,10],[10,15,5],[0,0,1],step_hours=1)
    np.testing.assert_allclose(got['total_cost'],[20,35,25])


def test_independent_piecewise_matches_absolute_value_identity():
    price=np.array([.3,.7,1.4])
    plan=np.array([800,2000,600])
    adjusted=np.array([1300,1000,600])
    emergency=np.array([2,3,0])
    got=settle_purchase(price,plan,adjusted,emergency)['total_cost']
    np.testing.assert_allclose(got,price*(adjusted+.5*np.abs(adjusted-plan)+5*emergency)/6)


@pytest.mark.parametrize('bad',[-1,float('nan'),float('inf')])
def test_invalid_values_are_not_silently_zeroed(bad):
    with pytest.raises(ValueError):
        settle_purchase([1],[bad],[1],[0])


def test_shapes_do_not_silently_broadcast():
    with pytest.raises(ValueError):
        settle_purchase([1,2],[1],[1,2],[0,0])


def test_storage_roundtrip_and_mismatched_path_detection():
    residual=storage_residual([6000,6090,6000],[600,0],[0,486])
    np.testing.assert_allclose(residual,[0,0],atol=1e-10)
    wrong=storage_residual([6000,6000,6000],[600,0],[0,486])
    assert np.max(np.abs(wrong))==pytest.approx(90)
