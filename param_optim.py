#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
@author: Qun Yang
@license: (C) Copyright 2021, University of Auckland
@contact: qyan327@aucklanduni.ac.nz
@date: 4/11/21 16:10
@description:  
@version: 1.0
"""


from models.base import BaseModel
from ileenet.objective.EnergyLoss import EnergyLoss
from ileenet.optimizer.SGD import SGD
from ileenet.optimizer.Adam import Adam
import numpy as np
from scipy.optimize import minimize, Bounds
import argparse
import json
import copy
import time


class ParamExp:

    def __init__(self, gm, args):
        self.gm = gm  # Ground motion
        self.args = args  # Initial parameters
        self.model = BaseModel(args)  # Model

    def energy_loss(self, params):
        output = self.model(self.gm['Data'], self.gm['Fs'], self.gm['Scale'], params)
        criteria = EnergyLoss(output)
        energy_loss = criteria()
        return energy_loss

    def search_params(self, params):
        bounds = Bounds([self.args.hw_lb, self.args.hc_lb, self.args.g_lb, self.args.rk_lb,
                         self.args.rc_lb, self.args.mu_lb],
                        [self.args.hw_rb, self.args.hc_rb, self.args.g_rb, self.args.rk_rb,
                         self.args.rc_rb, self.args.mu_rb])
        t1 = time.time()
        params_optim = minimize(self.energy_loss, params, method='SLSQP', jac='2-point',
                                options={'ftol': 1e-9, 'disp': True}, bounds=bounds)
        t2 = time.time()
        print('Time cost: {:.2f}s'.format(t2 - t1))
        np.save('./results/optim_params_{}_{}_{}_{}_{}_{}_{}.npy'.
                format(self.args.gm, self.args.h_w, self.args.h_c, self.args.g,
                       self.args.r_k, self.args.r_c, self.args.mu), params_optim.x)
        print(params_optim)
        return params_optim

    def energy_loss_(self, params):
        output = self.model(self.gm['Data'], self.gm['Fs'], self.gm['Scale'], params)
        criteria = EnergyLoss(output)
        energy_loss = criteria()
        return energy_loss, output

    def gradient_lagrangian(self, params, lambdas, h=0.1):
        grads = np.zeros_like(params)
        # h = np.array([10, 10, 0.1, 1, 1, 0.00001])
        for idx in range(len(params)):
            # print('Param {} computing gradient...'.format(idx + 1))
            # print(idx)
            param_tmp = copy.deepcopy(params)
            a = param_tmp[idx]
            param_tmp[idx] = a + h
            loss1, _ = self.energy_loss_(param_tmp)
            param_tmp[idx] = a - h
            loss2, _ = self.energy_loss_(param_tmp)
            grads[idx] = (loss1 - loss2) / (2 * h) + lambdas[2 * idx] - lambdas[2 * idx + 1]
        return grads

    def gradient_lambda(self, params):
        bounds = np.array([self.args.hw_lb, self.args.hw_rb, self.args.hc_lb, self.args.hc_rb,
                           self.args.g_lb, self.args.g_rb,
                           self.args.rk_lb, self.args.rk_rb, self.args.rc_lb, self.args.rc_rb,
                           self.args.mu_lb, self.args.mu_rb])
        grads_lambda = np.zeros_like(bounds)
        for idx, param in enumerate(params):
            grads_lambda[2 * idx] = param - bounds[2 * idx + 1]
            grads_lambda[2 * idx + 1] = - param + bounds[2 * idx]
        return grads_lambda

    def update_param(self, params, lambdas):
        # optimizer = SGD(params, lr=self.args.lr, momentum=self.args.momentum)
        # lr = np.array([1e-3, 1e-3, 1e-7, 1e-6, 1e-6, 1e-6])
        # lr_lambda = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1e-7, 1e-7, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6])
        if self.args.optimizer == 'SGD':
            optimizer = SGD(lr=self.args.lr, momentum=self.args.momentum)
            v = np.zeros_like(params)
            s, r = None, None
        else:
            optimizer = Adam(lr=self.args.lr, betas=(self.args.beta_1, self.args.beta_2))
            s, r = np.zeros_like(params), np.zeros_like(params)
            v = None
        param_names = ['h_w', 'h_c', 'g', 'r_k', 'r_c', 'mu']
        optim_history = {}
        for epoch in range(self.args.num_epoch):
            optim_history[epoch + 1] = {}
            t1 = time.time()
            for _ in range(10):
                grads_lambda = self.gradient_lambda(params)
                lambdas += np.multiply(self.args.lr, grads_lambda)
            print('Lambda: {}'.format(lambdas))
            grads = self.gradient_lagrangian(params, lambdas)
            grad_norm = np.linalg.norm(grads, ord=2)
            print('Grads: {}'.format(grads))
            print('Grad norm: {:.2f}'.format(grad_norm))
            if self.args.optimizer == 'SGD':
                params, v = optimizer.step(params, grads, v)
            else:
                params, s, r = optimizer.step(params, grads, s, r, epoch + 1)
            print('\033[1;34mh_w: {:.6f} h_c:{:.6f} g:{:.6f} r_k: {:.6f} r_c: {:.6f} mu :{:.6f}\033[0m'.
                  format(params[0], params[1], params[2], params[3], params[4], params[5]))
            energy_loss, output = self.energy_loss_(params)
            # np.save('./results/outputs/{}_{}.npy'.format(self.args.test, epoch + 1), output.u_tt)
            for idx, param_name in enumerate(param_names):
                optim_history[epoch + 1][param_name] = params[idx]
            optim_history[epoch + 1]['Energy loss'] = energy_loss
            t2 = time.time()
            print('\033[1;31mEpoch: {}\033[0m\t'
                  '\033[1;32mEnergy loss: {:.2f}\033[0m\t'
                  '\033[1;33mTime cost: {:.2f}s\033[0m'.format(epoch + 1, energy_loss, t2 - t1))
            print('\033[1;31m----------------------------------------------------------\033[0m')
            if grad_norm <= self.args.grad_tol:
                break
        optim_history = json.dumps(optim_history, indent=2)
        with open('./results/optim history_{}_{}_{}_{}.json'.
                  format(self.args.gm, self.args.optimizer, self.args.lr, self.args.num_epoch), 'w') as f:
            f.write(optim_history)
        return params


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # Initial parameters to be tuned
    parser.add_argument('--h_w', default=2000, type=float)  # Height of wall section
    parser.add_argument('--h_c', default=400, type=float)  # Height of column section
    parser.add_argument('--g', default=1, type=float)  # Gap
    parser.add_argument('--r_k', default=1000, type=float)  # Ratio of stiffness after contact to before
    parser.add_argument('--r_c', default=1000, type=float)  # Ratio of damping coefficient after contact to before
    parser.add_argument('--mu', default=0.1, type=float)  # Friction coefficient
    # Fixed parameters
    parser.add_argument('--k_c1', default=10, type=float)  # Stiffness before contact
    parser.add_argument('--c_c1', default=0.001, type=float)  # Damping coefficient before contact
    parser.add_argument('--g_tol', default=1e-8, type=float)  # Gap tolerance
    parser.add_argument('--xi', default=0.05, type=float)  # Crucial damping coefficient
    parser.add_argument('--b_w', default=150, type=float)  # Width of wall section
    parser.add_argument('--h', default=3000, type=float)  # Story height
    parser.add_argument('--mb', default=3.545, type=float)  # Mass block
    parser.add_argument('--alpha', default=0.9, type=float)  # PT coefficient
    parser.add_argument('--f_y', default=1137, type=float)  # Yield strength of PT bar
    parser.add_argument('--d', default=32, type=float)  # Diameter of PT bar
    parser.add_argument('--num_bar', default=2, type=int)  # Number of PT bars
    parser.add_argument('--rou', default=2.5e-9, type=int)  # Density of material
    parser.add_argument('--e', default=3e4, type=int)  # Young's elasticity modulus of material
    # Analysis hyper-parameters
    parser.add_argument('--gm', default='SLS-25', type=str)  # Ground motion
    parser.add_argument('--gm_dir', default='1', type=str)  # Ground motion direction
    parser.add_argument('--fs', default=200, type=float)  # Sampling frequency
    parser.add_argument('--scale', default=9800, type=float)  # Scale factor
    parser.add_argument('--integrator', default='Newmark', type=str)  # Integrator
    parser.add_argument('--algo', default='modified_newton', type=str)  # Iteration algorithm
    parser.add_argument('--convergence', default='disp', type=str)  # Convergence criteria
    parser.add_argument('--tol', default=1e-8, type=float)  # Convergence tolerance
    parser.add_argument('--max_iter', default=200, type=int)  # Maximum number of iterations
    # Optimize hyper-parameters
    parser.add_argument('--optimizer', default='SGD', type=str)  # Optimizer
    parser.add_argument('--grad_tol', default=1e-8, type=float)  # Gradient norm tolerance
    parser.add_argument('--lr', default=1e-8, type=float)  # Learning rate
    parser.add_argument('--momentum', default=0.9, type=float)  # Momentum
    parser.add_argument('--beta_1', default=0.9, type=float)  # Beta1
    parser.add_argument('--beta_2', default=0.999, type=float)  # Beta2
    parser.add_argument('--num_epoch', default=10, type=int)  # Number of epoch
    # Constraints
    parser.add_argument('--hw_lb', default=1500, type=float)
    parser.add_argument('--hw_rb', default=2500, type=float)
    parser.add_argument('--hc_lb', default=200, type=float)
    parser.add_argument('--hc_rb', default=700, type=float)
    parser.add_argument('--g_lb', default=0.5, type=float)
    parser.add_argument('--g_rb', default=10, type=float)
    parser.add_argument('--rk_lb', default=700, type=float)
    parser.add_argument('--rk_rb', default=1500, type=float)
    parser.add_argument('--rc_lb', default=700, type=float)
    parser.add_argument('--rc_rb', default=1500, type=float)
    parser.add_argument('--mu_lb', default=0.1, type=float)
    parser.add_argument('--mu_rb', default=0.5, type=float)
    args = parser.parse_args()
    gm_data = np.load('./data/{}.npy'.format(args.gm))
    gm = {'Data': gm_data, 'Fs': args.fs, 'Scale': args.scale}
    exp = ParamExp(gm, args)
    params = np.array([args.h_w, args.h_c, args.g, args.r_k, args.r_c, args.mu])  # Initial parameters
    # lambdas = np.array([1e4, 1e4, 1e4, 1e4, 1e5, 1e5, 1e4, 1e4, 1e4, 1e4, 1e3, 1e3])
    # params = exp.update_param(params, lambdas)
    params_optim = exp.search_params(params)