import torch
import torch.nn as nn
from torch.distributions import Normal
from torch.nn import functional as F


class BnnLayer(nn.Module):
    """
    Bayesian Neural Network Layer.

    Args:
        in_features (int): Number of input features.
        out_features (int): Number of output features.

    Attributes:
        in_features (int): Number of input features.
        out_features (int): Number of output features.
        weight_mu (nn.Parameter): Mean parameters for weight distribution.
        weight_std (nn.Parameter): Standard deviation parameters for weight distribution.
        bias_mu (nn.Parameter): Mean parameters for bias distribution.
        bias_std (nn.Parameter): Standard deviation parameters for bias distribution.

    Methods:
        reset_parameters(): Initialize parameters with specific initialization schemes.
        forward(x): Forward pass through the layer.

    """

    def __init__(self, in_features, out_features):
        super(BnnLayer, self).__init__()

        self.in_features = in_features
        self.out_features = out_features

        # Parameters for the weight distribution
        self.weight_mu = nn.Parameter(torch.Tensor(out_features, in_features))
        self.weight_std = nn.Parameter(torch.Tensor(out_features, in_features))

        # Parameters for the bias distribution
        self.bias_mu = nn.Parameter(torch.Tensor(out_features))
        self.bias_std = nn.Parameter(torch.Tensor(out_features))

        # Initialize parameters
        self.reset_parameters()

    def reset_parameters(self):
        """
        Initialize weight and bias parameters with specific initialization schemes.
        Weight parameters are initialized using Kaiming normal initialization,
        and standard deviation parameters are initialized with a constant value.
        Bias parameters are initialized with zeros, and bias standard deviation
        parameters are initialized with a constant value.
        """
        nn.init.kaiming_normal_(self.weight_mu, mode="fan_in", nonlinearity="relu")
        nn.init.constant_(self.weight_std, -5.0)

        nn.init.zeros_(self.bias_mu)
        nn.init.constant_(self.bias_std, -5.0)

    def forward(self, x):
        """
        Forward pass through the layer.

        Args:
            x (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Output tensor after the linear transformation.

        """
        # Sample weights and biases from normal distributions
        weight = Normal(self.weight_mu, torch.exp(self.weight_std)).rsample()
        bias = Normal(self.bias_mu, torch.exp(self.bias_std)).rsample()

        # Apply linear transformation to input using sampled weights and biases
        return F.linear(x, weight, bias)

    def kl_divergence(self):
        """
        Compute KL divergence between prior and approximate posterior for weights and biases.
        """
        weight_prior = Normal(
            torch.zeros_like(self.weight_mu), torch.exp(self.weight_std)
        )
        weight_posterior = Normal(self.weight_mu, torch.exp(self.weight_std))
        kl_weight = torch.distributions.kl.kl_divergence(
            weight_posterior, weight_prior
        ).sum()

        bias_prior = Normal(torch.zeros_like(self.bias_mu), torch.exp(self.bias_std))
        bias_posterior = Normal(self.bias_mu, torch.exp(self.bias_std))
        kl_bias = torch.distributions.kl.kl_divergence(bias_posterior, bias_prior).sum()

        return kl_weight + kl_bias


class BayesianModel(nn.Module):
    """
    Bayesian Neural Network Model.

    Args:
        input_size (int): Number of input features.
        hidden_size (int): Number of hidden units in the middle layer.
        output_size (int): Number of output features.

    Attributes:
        layer1 (BnnLayer): First Bayesian Neural Network layer.
        layer2 (BnnLayer): Second Bayesian Neural Network layer.

    Methods:
        forward(x): Forward pass through the model.

    """

    def __init__(self, input_size, hidden_size, output_size, num_layers):
        super(BayesianModel, self).__init__()

        self.layers = nn.ModuleList(
            [
                BnnLayer(input_size, hidden_size)
                if i == 0
                else BnnLayer(hidden_size, hidden_size)
                for i in range(num_layers)
            ]
        )
        self.output_layer = BnnLayer(hidden_size, output_size)

    def forward(self, x):
        """
        Forward pass through the model.

        Args:
            x (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Output tensor of the model.

        """
        # Apply ReLU activation to the output of the first layer
        for layer in self.layers:
            x = F.relu(layer(x))

        x = self.output_layer(x)
        return x

    def kl_divergence(self):
        """
        Compute total KL divergence for all layers in the model.
        """
        kl = 0
        for layer in self.layers:
            kl += layer.kl_divergence()
        kl += self.output_layer.kl_divergence()
        return kl

    def elbo_loss(self, x, y, num_samples=10):
        """
        Compute the Evidence Lower Bound (ELBO) loss for training the BNN.
        """
        outputs = []
        kl = self.kl_divergence()

        for _ in range(num_samples):
            output = self.forward(x)
            outputs.append(output)

        outputs = torch.stack(outputs)
        log_likelihood = Normal(outputs.mean(0), 1).log_prob(y).sum()

        elbo = log_likelihood - (kl / len(x))
        return -elbo  # Return negative ELBO as we want to minimize
