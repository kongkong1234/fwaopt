import os
import time
import numpy as np

EPS = 1e-8

class LoTFWA(object):

    def  __init__(self):
        # Definition of all parameters and states

        # evaluator
        self.evaluator = None

        # params
        self.fw_size = None
        self.sp_size = None
        self.init_amp = None
        self.gm_ratio = None

        # states
        self.pos = None
        self.fit = None

        # load default params
        self.set_params(self.default_params())

        # init states
        self.init_state()

    def default_params(self, benchmark=None):
        params = {}
        params['fw_size'] = 5
        params['sp_size'] = 300 if benchmark is None else 10*benchmark.dim
        params['init_amp'] = 200 if benchmark is None else benchmark.ub - benchmark.lb
        params['gm_ratio'] = 0.2
        return params
    
    def set_params(self, params):
        for param in params:
            setattr(self, param, params[param])

    def init_state(self):
        # init random seed
        self.seed = int(os.getpid()*time.clock())

    def opt(self, e):
        self.init_state()
        self.__init_fireworks(e)

        while not e.terminate():
            
            # allocate sparks
            num_sparks = [int(self.sp_size / self.fw_size)]*self.fw_size

            # explode
            sp = self.__explode(num_sparks)
            sf = e(sp)

            # mutate
            mp = self.__mutate(sp)
            mf = e(mp)

            # select
            n_pos, n_fit = self.__select([self.pos, self.fit], [sp, sf], [mp, mf])
            
            
            
    def __init_fireworks(self, e):
        self.pop = np.random.uniform(e.lb, e.ub, [self.fw_size, e.dim])
        self.fit = e(self.pop)

    def __explode(self, num_sparks):
        pass

    def __mutate(self):
        pass

    def run(self):
        # running time
        begin_time = time.clock()

        # init fireworks
        fireworks = np.random.uniform(self.lower_bound,
                                      self.upper_bound,
                                      [self.fw_size, self.dim])
        fits = self.evaluator(fireworks)
        amps = np.ones(self.fw_size) * self.init_amp
        
        best_idx = np.argmin(fits)
        best_idv = fireworks[best_idx, :]
        best_fit = fits[best_idx]

        # Start main loop
        
        # max iteration number should be computed according to specific algorithm
        max_iter = int(self.max_eval / self.sp_size)
        num_iter = 0
        num_eval = 0
        while True:
            if num_eval >= self.max_eval:
                break
            
            # compute explode sparks
            num_sparks = [int(self.sp_size / self.fw_size)]*self.fw_size # equal for LoTFWA 
            sum_sparks = np.sum(num_sparks)

            # explode
            e_sparks = []
            e_fits = []
            for idx in range(self.fw_size):
                bias = np.random.uniform(-1, 1, [num_sparks[idx], self.dim])
                sparks = fireworks[idx, :] + bias * amps[idx]
                sparks = self._map(sparks)
                spark_fits = self.evaluator(sparks)
                e_sparks.append(sparks)
                e_fits.append(spark_fits)
           
            # mutate
            m_sparks = []
            m_fits = []
            for idx in range(self.fw_size): 
                top_num = int(num_sparks[idx] * self.gm_ratio)
                sort_idx = np.argsort(e_fits[idx])
                top_idx = sort_idx[-top_num:]
                btm_idx = sort_idx[:top_num]

                top_mean = np.mean(e_sparks[idx][top_idx, :], axis=0)
                btm_mean = np.mean(e_sparks[idx][btm_idx, :], axis=0)
                delta = top_mean - btm_mean

                m_spark = fireworks[idx, :] + delta
                m_spark = self._map(m_spark)
                m_fit = self.evaluator(m_spark)
                m_sparks.append(m_spark)
                m_fits.append(m_fit)

            # select 
            n_fireworks = np.empty((self.fw_size, self.dim))
            n_fits = np.empty((self.fw_size))
            for idx in range(self.fw_size):
                sparks = np.concatenate([fireworks[idx, :][np.newaxis, :],
                                         e_sparks[idx],
                                         m_sparks[idx][np.newaxis, :]], axis=0)
                spark_fits = np.concatenate([[fits[idx]],
                                             e_fits[idx],
                                             [m_fits[idx]]], axis=0)
                min_idx = np.argmin(spark_fits)
                n_fireworks[idx, :] = sparks[min_idx, :]
                n_fits[idx] = spark_fits[min_idx]

            # restart
            improves = fits - n_fits
            min_fit = min(n_fits)
            restart = (improves > EPS) * (improves*(max_iter-num_iter) < (n_fits-min_fit))
            replace = restart[:, np.newaxis].astype(np.int32)
            restart_num = sum(replace)

            if restart_num > 0:
                rand_sample = np.random.uniform(self.lower_bound,
                                                self.upper_bound,
                                                (self.fw_size, self.dim))
                n_fireworks = (1-replace)*n_fireworks + replace*rand_sample
                n_fits[restart] = self.evaluator(n_fireworks[restart, :])
                amps[restart] = self.init_amp


            # update
            
            # dynamic amps
            for idx in range(self.fw_size):
                if n_fits[idx] < fits[idx] - EPS:
                    amps[idx] *= 1.2
                else:
                    amps[idx] *= 0.9
            
            # iter and eval num
            num_iter += 1
            num_eval += sum_sparks + self.fw_size + restart_num
            
            # record best results
            min_idx = np.argmin(n_fits)
            best_idv = n_fireworks[min_idx, :]
            best_fit = n_fits[min_idx]

            # new fireworks
            fireworks = n_fireworks
            fits = n_fits

        run_time = time.clock() - begin_time
        return best_fit, run_time
    
    def _map(self, samples):
        rand_samples = np.random.uniform(self.lower_bound,
                                         self.upper_bound,
                                         samples.shape)
        in_bound = (samples > self.lower_bound) * (samples < self.upper_bound)
        samples = in_bound * samples + (1 - in_bound) * rand_samples
        return samples
       
