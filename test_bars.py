import matplotlib.pyplot as plt
import numpy as np

methods = ["A", "B", "C", "D", "E"]
fig3_methods = methods
n_methods = len(methods)
width = 0.8 / n_methods
x = np.arange(9)
fig, ax = plt.subplots()

for i, method in enumerate(fig3_methods):
    vals = np.random.rand(9)
    ax.bar(
        x + (i - (n_methods - 1) / 2) * width,
        vals,
        width=width,
    )
plt.savefig("test_bars.png")
