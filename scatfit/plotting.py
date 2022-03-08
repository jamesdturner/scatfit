#
#   Plotting functions.
#   2022 Fabian Jankowski
#

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np

from scatfit.dm import get_dm_smearing
import scatfit.pulsemodels as pulsemodels


def use_custom_matplotlib_formatting():
    """
    Adjust the matplotlib configuration parameters for custom format.
    """

    matplotlib.rcParams["font.family"] = "serif"
    matplotlib.rcParams["font.size"] = 14.0
    matplotlib.rcParams["lines.markersize"] = 8
    matplotlib.rcParams["legend.frameon"] = False
    # make tickmarks more visible
    matplotlib.rcParams["xtick.major.size"] = 6
    matplotlib.rcParams["xtick.major.width"] = 1.5
    matplotlib.rcParams["xtick.minor.size"] = 4
    matplotlib.rcParams["xtick.minor.width"] = 1.5
    matplotlib.rcParams["ytick.major.size"] = 6
    matplotlib.rcParams["ytick.major.width"] = 1.5
    matplotlib.rcParams["ytick.minor.size"] = 4
    matplotlib.rcParams["ytick.minor.width"] = 1.5


def plot_frb(cand, plot_range, profile):
    """
    Plot the FRB data.
    """

    fig, (ax1, ax2, ax3) = plt.subplots(
        nrows=3,
        ncols=1,
        sharex="col",
        gridspec_kw={"height_ratios": [1, 1, 0.6], "hspace": 0},
    )

    ax1.step(
        plot_range,
        profile,
        where="mid",
        color="black",
        ls="solid",
        lw=1.0,
        zorder=3,
    )

    ax1.set_ylabel("Flux\n(a.u.)")
    ax1.tick_params(bottom=False)

    # plot dedispersed waterfall
    freqs = cand.chan_freqs
    chan_bw = np.diff(freqs)[0]

    print(cand.dedispersed.shape)
    quantiles = np.quantile(
        cand.dedispersed,
        q=[0.05, 0.1, 0.25, 0.3, 0.4, 0.5, 0.75, 0.8, 0.95, 0.97, 0.98, 0.99],
    )
    print(quantiles)

    ax2.imshow(
        cand.dedispersed.T,
        aspect="auto",
        interpolation=None,
        extent=[
            plot_range[0],
            plot_range[-1],
            freqs[-1] - 0.5 * chan_bw,
            freqs[0] + 0.5 * chan_bw,
        ],
        cmap="Greys",
        vmin=quantiles[0],
        vmax=quantiles[-4],
    )

    ax2.set_ylabel("Frequency\n(MHz)")
    ax2.tick_params(bottom=False)

    # plot dmt plane
    print(np.max(cand.dmt))
    print(np.min(cand.dmt))
    print(np.median(cand.dmt))

    dmt = cand.dmt
    dmt = dmt - np.median(dmt)

    ax3.imshow(
        dmt,
        aspect="auto",
        interpolation=None,
        cmap="Greys",
        vmax=0.4 * np.max(dmt),
        extent=[plot_range[0], plot_range[-1], 2.0 * cand.dm, 0],
    )

    ax3.set_ylim(bottom=1.2 * cand.dm, top=0.8 * cand.dm)
    ax3.set_ylabel("DM\n" + r"(pc cm$^{-3}$)")
    ax3.set_xlabel("Time (ms)")
    ax3.set_xlim(left=-70.0, right=70.0)

    # align ylabels horizontally
    fig.align_labels()

    fig.tight_layout()


def plot_profile_models():
    """
    Plot and compare the profile scattering models.
    """

    plot_range = np.linspace(-200.0, 200.0, num=2000)

    fig = plt.figure()
    ax = fig.add_subplot(111)

    ax.plot(
        plot_range,
        pulsemodels.scattered_profile(plot_range, 1.0, 0.0, 1.5, 2.5, 0.1),
        lw=2,
        label="convolved",
    )

    ax.plot(
        plot_range,
        pulsemodels.scattered_profile(plot_range, 2.0, 20.0, 1.5, 2.5, 0.1),
        lw=2,
        label="convolved",
    )

    ax.plot(
        plot_range,
        pulsemodels.scattered_gaussian_pulse(plot_range, 5.0, 0.0, 1.5, 2.5, 0.1),
        lw=2,
        label="analytic",
    )

    ax.plot(
        plot_range,
        pulsemodels.gaussian_scattered_afb_instrumental(
            plot_range, 5.0, 0.0, 1.5, 2.5, 0.306, 2.0, 0.1
        ),
        lw=2,
        label="afb",
    )

    ax.plot(
        plot_range,
        pulsemodels.gaussian_scattered_dfb_instrumental(
            plot_range, 5.0, 0.0, 1.5, 2.5, 4.0, 0.1
        ),
        lw=2,
        label="dfb",
    )

    ax.grid()
    ax.legend(loc="best")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Flux (a.u.)")

    fig.tight_layout()


def plot_profile_fit(fit_range, sub_profile, fitresult, iband):
    """
    Plot the profile fit.
    """

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


def plot_width_scaling(t_df, cand):
    """
    Plot the scaling of fitted widths with frequency.
    """

    df = t_df.copy()

    freqs = cand.chan_freqs
    chan_bw = np.diff(freqs)[0]

    fig = plt.figure()
    ax = fig.add_subplot()

    ax.errorbar(
        x=1e-3 * df["cfreq"],
        y=df["fwhm"],
        yerr=df["err_fwhm"],
        fmt="o",
        color="black",
        zorder=5,
        label="FWHM",
    )

    ax.errorbar(
        x=1e-3 * df["cfreq"],
        y=df["taus"],
        yerr=df["err_taus"],
        fmt="x",
        color="dimgrey",
        zorder=4,
        label=r"$\tau_\mathrm{s}$",
    )

    # intra-channel dispersive smearing
    f_lo = np.sort(freqs)
    f_hi = f_lo + np.abs(chan_bw)

    dm_smear = get_dm_smearing(f_lo * 1e-3, f_hi * 1e-3, cand.dm)

    ax.plot(
        1e-3 * 0.5 * (f_lo + f_hi),
        dm_smear,
        color="grey",
        ls="dashed",
        lw=2.0,
        zorder=3,
        label="smearing",
    )

    # instrumental smearing
    instrumental_smear = np.full(len(f_lo), 0.30624)

    ax.plot(
        1e-3 * 0.5 * (f_lo + f_hi),
        instrumental_smear,
        color="grey",
        ls="dotted",
        lw=2.0,
        zorder=3,
        label="instrumental",
    )

    ax.grid()
    ax.legend(loc="best", frameon=False)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Width (ms)")
    ax.set_xscale("log")
    ax.set_yscale("log")

    sfor = FormatStrFormatter("%g")
    ax.xaxis.set_major_formatter(sfor)
    ax.xaxis.set_minor_formatter(sfor)
    ax.yaxis.set_major_formatter(sfor)

    fig.tight_layout()

    fig.savefig("width_scaling.pdf", bbox_inches="tight")