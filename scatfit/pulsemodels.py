#
#   Pulse models.
#   2022 Fabian Jankowski
#

import numpy as np
from scipy import signal, special


def gaussian_normed(x, fluence, center, sigma):
    """
    A normed Gaussian function.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    res = (
        fluence
        / (sigma * np.sqrt(2.0 * np.pi))
        * np.exp(-0.5 * np.power((x - center) / sigma, 2))
    )

    return res


def scattered_gaussian_pulse(x, fluence, center, sigma, taus, dc):
    """
    A scattered Gaussian pulse. Analytical approach, assuming thin screen scattering.

    We use a standard implementation of an exponentially modified gaussian here, see
    https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.exponnorm.html

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.
    taus: float
        The scattering time.
    dc: float
        The vertical offset of the profile from the baseline.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    # treat the following special cases
    # 1) invK >> 1, i.e. sigma >> taus
    # -> function becomes a regular gaussian

    invsigma = 1.0 / sigma
    K = taus * invsigma
    invK = 1.0 / K
    y = (x - center) * invsigma

    if invK >= 10.0:
        res = dc + gaussian_normed(x, fluence, center, sigma)
    else:
        argexp = 0.5 * invK**2 - y * invK

        # prevent numerical overflows
        mask = argexp >= 300.0
        argexp[mask] = 0.0

        exgaussian = (
            0.5
            * invK
            * invsigma
            * np.exp(argexp)
            * special.erfc(-(y - invK) / np.sqrt(2.0))
        )

        res = dc + fluence * exgaussian

    return res


def gaussian_scattered_afb_instrumental(
    x, fluence, center, sigma, taus, taui, taud, dc
):
    """
    A Gaussian pulse scattered in the ISM and affected by analogue
    (single-sided exponential) instrumental effects from DM-smearing and
    the detector/signal chain.

    This implements Eq. 7 from McKinnon 2014.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.
    taus: float
        The scattering time in the ISM.
    taui: float
        The scattering time due to instrumental effects in the receiver or signal chain
        (e.g. integration time constant).
    taud: float
        The scattering time due to intra-channel dispersive smearing.
    dc: float
        The vertical offset of the profile from the baseline.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    A = (
        np.power(taus, 2)
        * scattered_gaussian_pulse(x, fluence, center, sigma, taus, 0.0)
        / ((taus - taui) * (taus - taud))
    )

    B = (
        np.power(taui, 2)
        * scattered_gaussian_pulse(x, fluence, center, sigma, taui, 0.0)
        / ((taus - taui) * (taui - taud))
    )

    C = (
        np.power(taud, 2)
        * scattered_gaussian_pulse(x, fluence, center, sigma, taud, 0.0)
        / ((taus - taud) * (taui - taud))
    )

    res = dc + A - B + C

    return res


def boxcar(x, width):
    """
    A simple boxcar function.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    width: float
        The width of the boxcar function.

    Returns
    -------
    res: ~np.array
        The boxcar data.
    """

    res = np.zeros(len(x))

    mask = np.abs(x) <= 0.5 * width
    res[mask] = 1.0

    return res


def gaussian_scattered_dfb_instrumental(x, fluence, center, sigma, taus, taud, dc):
    """
    A Gaussian pulse scattered in the ISM and affected by digital (boxcar-like) instrumental effects.
    Convolving approach. We neglect instumental receiver or signal chain effects.

    This implements Eq. 2 from Loehmer et al. 2001.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.
    taus: float
        The scattering time in the ISM.
    taud: float
        The scattering time due to intra-channel dispersive smearing.
    dc: float
        The vertical offset of the profile from the baseline.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    A = scattered_profile(x, fluence, center, sigma, taus, 0.0)

    B = boxcar(x, taud)

    res = dc + signal.oaconvolve(A, B, mode="same") / np.sum(B)

    return res


def gaussian_fwhm(sigma):
    """
    The full width at half maximum (W50) of a Gaussian.

    Parameters
    ----------
    sigma: float
        The Gaussian standard deviation.

    Returns
    -------
    res: float
        The Gaussian W50.
    """

    res = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma

    return res


def gaussian_fwtm(sigma):
    """
    The full width at tenth maximum (W10) of a Gaussian.

    Parameters
    ----------
    sigma: float
        The Gaussian standard deviation.

    Returns
    -------
    res: float
        The Gaussian W10.
    """

    res = 2.0 * np.sqrt(2.0 * np.log(10.0)) * sigma

    return res


def equivalent_width(x, amp):
    """
    Compute the boxcar equivalent width.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    amp: ~np.array
        The pulse amplitude.

    Returns
    -------
    weq: float
        The equivalent width.
    """

    mask = amp >= 0
    fluxsum = np.sum(amp[mask]) * np.abs(x[0] - x[1])
    weq = fluxsum / np.max(amp)

    return weq


def full_width_post(x, amp, level):
    """
    Compute the full pulse width post scattering numerically.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    amp: ~np.array
        The pulse amplitude.
    level: float
        The level at which to evaluate the pulse width.

    Returns
    -------
    width: float
        The full pulse width at the given level.
    """

    mask = amp >= level * np.max(amp)

    # treat special case when pulse is only one sample wide
    if len(x[mask]) > 1:
        width = np.abs(np.max(x[mask]) - np.min(x[mask]))
    else:
        width = np.abs(x[0] - x[1])

    return width


def pbf_isotropic(x, taus):
    """
    A pulse broadening function for isotropic scattering.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    taus: float
        The scattering time.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    res = np.zeros(len(x))

    invtaus = 1.0 / taus

    mask = x >= 0.0
    res[mask] = invtaus * np.exp(-x[mask] * invtaus)

    return res


def scattered_profile(x, fluence, center, sigma, taus, dc):
    """
    A scattered pulse profile.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.
    taus: float
        The scattering time.
    dc: float
        The vertical offset of the profile from the baseline.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    A = gaussian_normed(x, fluence, center, sigma)

    B = pbf_isotropic(x, taus)

    scattered = dc + signal.oaconvolve(A, B, mode="same") / np.sum(B)

    return scattered


def bandintegrated_model(x, fluence, center, sigma, taus, dc, f_lo, f_hi, nfreq):
    """
    A true frequency band-integrated profile model.

    The total (sub-)band-integrated profile is the superposition (weighted sum or
    weighted mean) of several profiles that evolve with frequency across the bandwidth
    of the frequency (sub-)band, one for each frequency channel. Namely, the individual
    profiles evolve with frequency (scattering, pulse width, fluence). For large
    fractional bandwidths or at low frequencies (< 1 GHz), the profile evolution across
    the band cannot be neglected, i.e. the narrow-band approximation fails.

    We compute the frequency evolution across the band between `f_lo` and `f_hi` at
    `nfreq` centre frequencies. The total profile is then the weighted sum over the
    finite frequency grid. Ideally, one would use an infinitesimally narrow grid here.

    Parameters
    ----------
    x: ~np.array
        The running variable (time).
    fluence: float
        The fluence of the pulse, i.e. the area under it.
    center: float
        The mean of the Gaussian, i.e. its location.
    sigma: float
        The Gaussian standard deviation.
    taus: float
        The scattering time.
    dc: float
        The vertical offset of the profile from the baseline.
    f_lo: float
        The centre frequency of the lowest channel in the sub-band.
    f_hi: float
        The centre frequency of the highest channel in the sub-band.
    nfreq: int
        The number of centre frequencies to evaluate.

    Returns
    -------
    res: ~np.array
        The profile data.
    """

    band_cfreq = 0.5 * (f_lo + f_hi)

    # the low-frequency profiles dominate the total band-integrated
    # profile because of the strong fluence power law scaling
    # use finer steps towards the low-frequency band edge
    cfreqs = np.geomspace(f_lo, f_hi, num=nfreq)

    taus_s = taus * np.power(cfreqs / band_cfreq, -4.0)
    fluence_s = fluence * np.power(cfreqs / band_cfreq, -1.5)

    profiles = np.zeros(shape=(nfreq, len(x)))

    for i in range(nfreq):
        profiles[i, :] = scattered_gaussian_pulse(
            x, fluence_s[i], center, sigma, taus_s[i], 0.0
        )

    # sum, weighted by fluence above
    res = np.sum(profiles, axis=0)

    # normalise to match input fluence
    tot_fluence = np.sum(res) * np.abs(x[0] - x[1])
    res = dc + (fluence / tot_fluence) * res

    return res
