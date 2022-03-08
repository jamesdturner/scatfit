#
#   Fit scattering models to FRB data.
#   2022 Fabian Jankowski
#

import argparse
import sys

import corner
from iqrm import iqrm_mask
from lmfit import Model
import matplotlib.pyplot as plt
from mtcutils.core import normalise, zdot
import numpy as np
import pandas as pd
import your
from your.candidate import Candidate

from scatfit.dm import get_dm_smearing
import scatfit.plotting as plotting
import scatfit.pulsemodels as pulsemodels


def parse_args():
    """
    Parse the commandline arguments.

    Returns
    -------
    args: populated namespace
        The commandline arguments.
    """

    parser = argparse.ArgumentParser(
        description="Fit a scattering model to FRB data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "filename", type=str, help="The name of the input filterbank file."
    )

    parser.add_argument(
        "dm",
        type=float,
        help="The dispersion measure of the FRB.",
    )

    parser.add_argument(
        "--fscrunch",
        dest="fscrunch_factor",
        default=256,
        metavar="factor",
        type=int,
        help="Integrate this many frequency channels.",
    )

    parser.add_argument(
        "--tscrunch",
        dest="tscrunch_factor",
        default=1,
        metavar="factor",
        type=int,
        help="Integrate this many time samples.",
    )

    parser.add_argument(
        "--smodel",
        dest="smodel",
        choices=[
            "unscattered",
            "scattered_isotropic",
            "scattered_isotropic_afb_instrumental",
            "scattered_isotropic_dfb_instrumental",
        ],
        default="scattered_isotropic_dfb_instrumental",
        help="Use the specified scattering model.",
    )

    parser.add_argument(
        "--showmodels",
        action="store_true",
        dest="show_models",
        default=False,
        help="Show comparison plot of scattering models.",
    )

    args = parser.parse_args()

    return args


def fit_profile_model(fit_range, profile, dm_smear):
    """
    Fit a profile model to data.
    """

    model = Model(pulsemodels.gaussian_scattered_dfb_instrumental)

    model.set_param_hint("fluence", value=5.0, min=0.1)
    model.set_param_hint("center", value=0.0, min=-20.0, max=20.0)
    model.set_param_hint("sigma", value=1.0, min=0.1, max=20.0)
    model.set_param_hint("taus", value=0.5, min=0.01, max=20.0)
    model.set_param_hint("taud", value=dm_smear, vary=False)
    model.set_param_hint("dc", value=0.0, min=-0.3, max=0.3)

    fitparams = model.make_params()

    fitparams.add("fwhm", expr="2.3548200*sigma")
    fitparams.add("fwtm", expr="4.2919320*sigma")

    fitresult_ml = model.fit(
        data=profile, x=fit_range, params=fitparams, method="leastsq"
    )

    if not fitresult_ml.success:
        raise RuntimeError("Fit did not converge.")

    print(fitresult_ml.fit_report())

    # emcee_kws = dict(steps=300, burn=100, thin=20, is_weighted=False, progress=True)
    emcee_kws = dict(steps=6000, burn=700, thin=20, is_weighted=False, progress=True)

    emcee_params = fitresult_ml.params.copy()
    emcee_params.add("__lnsigma", value=np.log(0.1), min=np.log(0.001), max=np.log(2.0))

    fitresult_emcee = model.fit(
        data=profile,
        x=fit_range,
        params=emcee_params,
        method="emcee",
        fit_kws=emcee_kws,
    )

    print(fitresult_emcee.fit_report())

    # get maximum likelihood values
    max_likelihood = np.argmax(fitresult_emcee.lnprob)
    max_likelihood_idx = np.unravel_index(max_likelihood, fitresult_emcee.lnprob.shape)
    max_likelihood_values = fitresult_emcee.chain[max_likelihood_idx]

    corner.corner(
        fitresult_emcee.flatchain,
        labels=fitresult_emcee.var_names,
        truths=max_likelihood_values,
        quantiles=[0.16, 0.5, 0.84],
        show_titles=True,
        title_kwargs={"fontsize": 10},
    )

    return fitresult_emcee


def fit_profile(cand, plot_range, fscrunch_factor):
    """
    Fit an FRB profile.
    """

    df = pd.DataFrame(
        columns=[
            "band",
            "cfreq",
            "fluence",
            "err_fluence",
            "sigma",
            "err_sigma",
            "taus",
            "err_taus",
            "taud",
        ]
    )
    freqs = cand.chan_freqs
    chan_bw = np.diff(freqs)[0]

    for iband in range(cand.dedispersed.T.shape[0]):
        print("Running sub-band: {0}".format(iband))

        sub_profile = cand.dedispersed.T[iband]

        # select only the central +- 200 ms around the frb for the fit
        mask = np.abs(plot_range) <= 200.0
        fit_range = np.copy(plot_range[mask])
        sub_profile = sub_profile[mask]

        # remove baseline and normalise
        sub_profile = sub_profile - np.mean(sub_profile)
        sub_profile = sub_profile / np.max(sub_profile)

        # compute baseline statistics outside the central +- 20 ms
        mask = np.abs(fit_range) > 20.0
        quantiles = np.quantile(sub_profile[mask], q=[0.25, 0.75], axis=None)
        std = 0.7413 * np.abs(quantiles[1] - quantiles[0])
        snr = np.max(sub_profile) / std
        print("S/N: {0:.2f}".format(snr))

        # if not snr >= 4.0:
        if not snr >= 3.7:
            print("Profile S/N too low: {0:.2f}".format(snr))
            continue

        cfreq = freqs[0] + (0.5 + iband) * fscrunch_factor * chan_bw
        f_lo = cfreq - 0.5 * np.abs(chan_bw)
        f_hi = cfreq + 0.5 * np.abs(chan_bw)

        dm_smear = get_dm_smearing(f_lo * 1e-3, f_hi * 1e-3, cand.dm)

        print(
            "Frequencies (MHz), DM smearing (ms): {0:.2f} {1:.2f} {2:.2f} {3:.2f}".format(
                f_lo, cfreq, f_hi, dm_smear
            )
        )

        fitresult = fit_profile_model(fit_range, sub_profile, dm_smear)

        # compute profile statistics
        fluxsum = (
            np.sum(fitresult.best_fit[fitresult.best_fit >= 0])
            * np.abs(np.diff(fit_range))[0]
        )
        weq = fluxsum / np.max(fitresult.best_fit)

        temp = pd.DataFrame(
            {
                "band": iband,
                "cfreq": cfreq,
                "fluence": fitresult.best_values["fluence"],
                "err_fluence": fitresult.params["fluence"].stderr,
                "sigma": fitresult.best_values["sigma"],
                "err_sigma": fitresult.params["sigma"].stderr,
                "taus": fitresult.best_values["taus"],
                "err_taus": fitresult.params["taus"].stderr,
                "taud": fitresult.best_values["taud"],
                "fluxsum": fluxsum,
                "weq": weq,
            },
            index=[iband],
        )

        df = pd.concat([df, temp], ignore_index=True)

        fig = plt.figure()
        ax = fig.add_subplot(111)

        ax.step(
            fit_range,
            sub_profile,
            where="mid",
            color="black",
            ls="solid",
            lw=1.0,
            zorder=3,
        )

        ax.plot(
            fit_range,
            fitresult.init_fit,
            color="tab:blue",
            ls="dotted",
            lw=1.5,
            zorder=6,
        )

        ax.plot(
            fit_range,
            fitresult.best_fit,
            color="tab:red",
            ls="dashed",
            lw=2.0,
            zorder=8,
        )

        ax.set_title("Sub-band {0}".format(iband))
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Flux (a.u.)")
        ax.set_xlim(left=-50.0, right=50.0)

        fig.tight_layout()

    # compute fwhm and fwtm
    df["fwhm"] = pulsemodels.gaussian_fwhm(df["sigma"])
    df["err_fwhm"] = pulsemodels.gaussian_fwhm(df["err_sigma"])
    df["fwtm"] = pulsemodels.gaussian_fwtm(df["sigma"])
    df["err_fwtm"] = pulsemodels.gaussian_fwtm(df["err_sigma"])

    return df


#
# MAIN
#

def main():
    args = parse_args()

    plotting.use_custom_matplotlib_formatting()

    if args.show_models:
        plotting.plot_profile_models()
        plt.show()
        sys.exit(0)

    yobj = your.Your(args.filename)
    print(yobj.your_header)
    data = yobj.get_data(nstart=0, nsamp=yobj.your_header.nspectra)

    spectral_std = np.std(data, axis=0)
    mask, _ = iqrm_mask(
        spectral_std, radius=int(0.1 * yobj.your_header.nchans), threshold=3
    )
    print("IQRM channel mask: {}".format(np.where(mask)[0]))

    cand = Candidate(
        fp=args.filename,
        dm=args.dm,
        tcand=0.0,
        width=2,
        label=-1,
        device=0,
    )

    cand.get_chunk()
    data = cand.data

    print("Data shape: {0}".format(data.shape))

    # normalise the data
    data = data.astype(np.float32).T
    data, _, _ = normalise(data)

    # run zdot filter
    # this acts like a zerodm filter
    data = zdot(data)
    data = data.T

    print("Data shape: {0}".format(data.shape))

    # apply iqrm mask
    data[:, mask] = 0

    # the bottom of the band is always bad
    # data[:, 1000:] = 0
    # data[:, 920:] = 0

    cand.data = data
    cand.dedisperse()
    cand.dmtime(dmsteps=2048)

    # scrunch
    cand.decimate(
        key="ft", axis=0, pad=True, decimate_factor=args.tscrunch_factor, mode="median"
    )

    cand.decimate(
        key="ft", axis=1, pad=True, decimate_factor=args.fscrunch_factor, mode="median"
    )

    cand.decimate(
        key="dmt", axis=1, pad=True, decimate_factor=args.tscrunch_factor, mode="median"
    )

    # band-integrated profile
    profile = np.sum(cand.dedispersed.T, axis=0)
    profile = profile - np.mean(profile)
    profile = profile / np.max(profile)

    fact = 1000 * cand.tsamp * args.tscrunch_factor
    plot_range = np.linspace(0, fact * len(profile), num=len(profile))

    # centre on the burst
    bin_burst = np.argmax(profile)
    plot_range -= fact * bin_burst

    # fit integrated profile
    fit_df = fit_profile(cand, plot_range, args.fscrunch_factor)

    print(fit_df)
    plotting.plot_width_scaling(fit_df, cand)

    plotting.plot_frb(cand, plot_range, profile)

    plt.show()

    print("All done.")


if __name__ == "__main__":
    main()
