# HPC Cluster Documentation - Complete Reference

<llm_instructions>
You are answering questions about the UMC Utrecht HPC cluster (SLURM-based). This document contains the complete cluster documentation.

HOW TO USE THIS DOCUMENT:
1. Scan the Table of Contents below - each entry has a 1-2 sentence summary describing what that section covers
2. Use the summaries to identify which section(s) are relevant to the user's query
3. Jump to the relevant section using the line number reference (e.g., "line 1348")
4. Quote specific commands, flags, and configuration examples directly from the documentation
5. For multi-part questions, gather information from multiple sections before responding

QUERY ROUTING:
- "How do I connect/login" → Login & Access section (check OS-specific subsection)
- "How do I submit a job / run code" → SLURM Guide section
- "How do I install software / use conda" → Software & Environments section
- "GPU / graphics card" → SLURM Guide (GPU subsection) + GPU Nodes specs
- "Transfer files / copy data" → Data Management section
- "What nodes/resources are available" → Cluster Setup & Resources section
- "Web interface / browser access" → Open OnDemand section
- "Workflow / pipeline / WDL" → Cromwell section

COMMON PATTERNS TO EXTRACT:
- SLURM commands: sbatch, srun, salloc, squeue, scancel + their flags
- Resource requests: --mem, --time, -c, --gres, --gpus-per-node, -p (partition)
- SSH commands: ssh -l user host, ssh-keygen, ProxyJump configs
- Module commands: module load/avail/list/purge
- Conda commands: conda create/activate/install, channel configuration

When the user's query matches documentation content, provide the specific commands/syntax from this document rather than generic advice.
</llm_instructions>

---

## Table of Contents

### Quick Start & Basics
*Initial setup, common questions, productivity tips. Start here for new users or quick command references.*

- **[Quick Start Guide](#quick-start-guide)** *(line 103)* — SSH client setup (PuTTY/MobaXterm/native), login commands for hpcs05/hpcs06, key generation for external access. Covers: ssh -l username hpcs05.op.umcutrecht.nl, public key submission to hpcsupport@umcutrecht.nl.
- **[FAQ](#faq)** *(line 166)* — Common user questions about HPC access, job submission, and troubleshooting. Includes password reset procedures and basic cluster information.
- **[Tips & Tricks](#tips-tricks)** *(line 200)* — Productivity shortcuts: hpcstats monitoring URLs, shell aliases, workflow optimizations. Contains quick command references for power users.
- **[How-To Guides](#how-to-guides)** *(line 270)* — Comprehensive task recipes: sbatch job submission, array jobs (--array), srun interactive sessions, MPI setup (module load openmpi, mpicc, mpirun -np), GPU access (-p gpu --gpus-per-node), R/Matlab/Bioperl setup, SSH proxy configs, debugging tips (strace, bash -x).

### Login & Access
*SSH connection methods by OS. Query this for connection problems, key setup, or platform-specific instructions.*

- **[Login Overview](#login-overview)** *(line 865)* — Entry point for all login methods. Links to OS-specific guides. Use when user asks 'how do I connect' without specifying OS.
- **[Login from Linux / Mac](#login-from-linux-mac)** *(line 899)* — Native SSH client usage: ssh-keygen -t ed25519, ssh-copy-id, ~/.ssh/config ProxyJump setup for gateway access. Covers internal (direct) and external (via hpcgw.op.umcutrecht.nl) connections.
- **[Login from Windows](#login-from-windows)** *(line 1068)* — Windows SSH options overview: native PowerShell ssh, PuTTY, MobaXterm. Key generation with ssh-keygen, external access requirements.
- **[Login with PuTTY](#login-with-putty)** *(line 1083)* — PuTTY configuration: Session setup for hpcs05/hpcs06, Connection>Data username, puttygen key generation (ED25519), Pageant key agent, tunneling for gateway access.
- **[Login with MobaXterm](#login-with-mobaxterm)** *(line 1158)* — MobaXterm setup: Session creation, built-in X11 forwarding, SFTP file browser, key generation via Tools>MobaKeyGen, gateway tunneling configuration.
- **[Login with PowerShell](#login-with-powershell)** *(line 1243)* — Windows native SSH: ssh-keygen in PowerShell, .ssh folder setup, config file for ProxyJump through gateway, ssh-agent service configuration.

### SLURM Job Scheduler
*Job submission, resource requests, queues, GPU allocation. Primary reference for running compute jobs.*

- **[SLURM Guide](#slurm-guide)** *(line 1408)* — Complete SLURM reference: srun (interactive), sbatch (batch), salloc (allocation). Partitions: cpu (default), gpu. Resource flags: --mem, --time, -c (cpus), --gres=tmpspace:NNG, --gpus-per-node. GPU types: quadro_rtx_6000, tesla_v100, tesla_p100, a100. SGE migration table (qsub→sbatch, qstat→squeue, qdel→scancel). Resource limits per account group via showuserlimits. $TMPDIR=/scratch/$SLURM_JOB_ID for local scratch.

### Software & Environments
*Package management, modules, conda environments. Query for installing software or loading tools.*

- **[Software Overview](#software-overview)** *(line 1679)* — Software installation patterns: user-space installs in /hpc/local/Rocky8/<group>/, conda environments, R package installation (install.packages with lib path), Python venv setup, compiling from source. Covers permission model and group directories.
- **[Conda](#conda)** *(line 1897)* — Miniforge setup: wget Miniforge3-Linux-x86_64.sh, conda-forge channel default, bioconda channel addition. Environment management: conda create -n envname, conda activate. Migration from defaults channel to conda-forge.
- **[Lmod Modules](#lmod-modules)** *(line 1946)* — Environment modules: module avail, module load <name>, module list, module purge. Custom modulefiles in /hpc/local/Rocky8/<group>/modules/. Covers writing modulefiles with prepend_path and setenv.
- **[Migrating to conda-forge](#migrating-to-conda-forge)** *(line 2122)* — Channel migration procedure: backup existing env, conda config --add channels conda-forge, conda config --set channel_priority strict. Troubleshooting dependency conflicts.

### Cluster Setup & Resources
*Hardware specs, node types, organizational structure. Query for capacity planning or understanding available resources.*

- **[Setup Overview](#setup-overview)** *(line 2172)* — Cluster architecture overview: submit hosts (hpcs05/hpcs06), compute nodes, storage hierarchy (/home, /hpc/shared, /scratch). Account model, group directories, quota information.
- **[Cluster Architecture](#cluster-architecture)** *(line 2363)* — High-level cluster topology: login nodes, compute partitions, network fabric. Entry point to detailed node specifications.
- **[CPU Nodes](#cpu-nodes)** *(line 2375)* — CPU partition specs: node count, CPU models, cores per node, RAM per node, hyperthreading (SLURM 'cpu' = hyperthread). Useful for capacity planning sbatch requests.
- **[GPU Nodes](#gpu-nodes)** *(line 2439)* — GPU partition specs: GPU models (Tesla P100/V100, RTX 6000, A100), GPUs per node, VRAM, associated CPU/RAM. Request syntax: -p gpu --gpus-per-node=<type>:<count>.
- **[All Compute Nodes](#all-compute-nodes)** *(line 2525)* — Complete node inventory table: hostname, partition, CPUs, RAM, GPUs, local scratch. Reference for --nodelist targeting or understanding squeue output.
- **[HPC User Council](#hpc-user-council)** *(line 2607)* — Governance: user council meeting schedule, feedback channels, policy discussions. Contact for cluster-wide issues or feature requests.
- **[Participation Groups](#participation-groups)** *(line 2629)* — Account/group model: how compute allocations work, group membership, resource quotas. Explains -A/--account flag usage.

### Data Management
*File transfer methods, storage systems. Query for moving data to/from cluster.*

- **[Transferring Data](#transferring-data)** *(line 2664)* — Data transfer methods: scp, rsync, SFTP (via MobaXterm), Globus, SURFfilesender for large files. Internal paths, external transfer via gateway. Covers efficient large-dataset transfers.
- **[iRODS](#irods)** *(line 2755)* — iRODS data management system: icommands (iput, iget, ils), metadata, data policies. Integration with HPC workflows for managed research data.

### Additional Resources
*Web interfaces, workflow engines, policies, contacts. Query for GUI access, Cromwell/WDL, or administrative matters.*

- **[Open OnDemand](#open-ondemand)** *(line 2782)* — Web portal access: https://hpcs05.op.umcutrecht.nl or hpcs06. Features: file browser, job composer, interactive apps. Requires UMC network or VPN (vdi-ext.umcutrecht.nl, solisworkspace.uu.nl).
- **[RStudio Server](#rstudio-server)** *(line 2808)* — RStudio via Open OnDemand: launching sessions, resource allocation, package installation in user library. Alternative to command-line R.
- **[Cromwell Workflow Engine](#cromwell-workflow-engine)** *(line 2835)* — WDL workflow execution: Cromwell server setup, workflow submission API, job monitoring, SLURM backend configuration. Covers multi-step bioinformatics pipelines.
- **[Do's and Don'ts](#dos-and-donts)** *(line 3073)* — Cluster etiquette: don't run on login nodes, don't hog resources, do use scratch for temp files, do clean up. Policy violations and consequences.
- **[External Links](#external-links)** *(line 3086)* — Curated external resources: SLURM docs (slurm.schedmd.com), shell tools (shellcheck, explainshell), language tutorials, Apptainer/Docker docs.
- **[Conditions of Use](#conditions-of-use)** *(line 3107)* — Usage policy: acceptable use, data handling requirements, security obligations, account responsibilities. Required reading for compliance.
- **[Contact](#contact)** *(line 3180)* — Support contacts: hpcsupport@umcutrecht.nl for technical issues, account requests, access problems. Escalation paths.


---

---

# Quick Start & Basics

## Quick Start Guide

> **Summary:** SSH client setup (PuTTY/MobaXterm/native), login commands for hpcs05/hpcs06, key generation for external access. Covers: ssh -l username hpcs05.op.umcutrecht.nl, public key submission to hpcsupport@umcutrecht.nl.

For using the **HPC** you need an **ssh client**

\- for **MS-Windows** you can use the internal ssh client in a Powershell terminal or install a client with a graphical user interface: 
**MobaXterm**  see : <https://mobaxterm.mobatek.net/> 
  or 
**Putty **see : <https://www.putty.org/>

\- for **Mac and Linux** you can use the internal ssh client. 
       see :  **man ssh**

Inside the UMC **network** you can access the **HPC** by:



ssh -l myusername hpcs05.op.umcutrecht.nl 
or 
ssh -l myusername hpcs06.op.umcutrecht.nl 
or 
ssh -l myusername hpcsubmit.op.umcutrecht.nl



p.e. :  **ssh -l mvanburen hpcs05.op.umcutrecht.nl** 
and log in with the **password** you received from us.

\*\*

If you want to use the HPC **outside** the **UMC network** you have to :

Create **public** / **secret key**  combination  in ssh.

Sent only the "**public-key**" by **email**  to <hpcsupport@umcutrecht.nl>



How to create the key in Windows see : [Login - Windows](#login-from-windows)

How to create the key in Linux / Mac see : [Login - Linux / Mac](#login-from-linux-mac)



We configure the **public-key** on the gateway and you can **log in** on **hpcgw.op.umcutrecht.nl**

with your **selfmade  "passphrase" **.

Once on the gateway you can go to the HPC by :



ssh hpcs05 
or 
ssh hpcs06 
or 
ssh hpcsubmit



and log in with the "**password**"  (you receive from us on your mobile phone.)

## FAQ

> **Summary:** Common user questions about HPC access, job submission, and troubleshooting. Includes password reset procedures and basic cluster information.

## How many cores and how much memory should my job request

  
If you don't know how many cores (-c N), or how much memory (--mem=...G) your job needs, just don't specify anything; your job will then get 1 core and 10 GB of memory. For most jobs, this is plenty.

Your job will **not** run any faster by requesting more cores or memory. Your job will only run faster if you request more cores and memory **and use it**, which means that in most cases you have to specify to your program that it should use a certain number of threads (e.g., for bowtie2, you would do this with the = --threads = option).

Requesting huge amounts of cores and memory and not using it, needlessly prevents other jobs from running.

## Why doesn't my job run?

If your jobs stays in the "PD" (pending) state for a long time, there's several things that could be wrong. 
Some of these are pretty easy to spot, some are not :-). 
The last column of "squeue" (NODELIST (REASON)) will tell you the reason, is not always very easy to interpret. 
See "man squeue" (JOB REASON CODES).

Most likely:

- You're requesting resources (cores, memory) that are not currently available on any compute node. Wait for a bit, or scancel your job and resubmit with lower requirements.

Another possibility:

- There are limits on the amount of CPU and memory that any group can use at the same time. Maybe you (or another member of your group) is already using many CPU's or a large amount of memory.

And finally:

- There is a limit on how many jobs with how many cores can run with long runtimes.

This will be explained on a seperate page later. Ask  <hpcsupport@umcutrecht.nl>  for clarification for now.

## Tips & Tricks

> **Summary:** Productivity shortcuts: hpcstats monitoring URLs, shell aliases, workflow optimizations. Contains quick command references for power users.

**Show used resources of a completed job.**

**\# get list of your completed jobids** 
sacct --user mvanburen  --starttime=2022-11-10 \| grep -i completed

**\# show global info  of one of the jobids ** 
sacct -j 16333975 --format=jobid,jobname,ncpus,ntasks,timelimit,partition,state

**\# show runtime  info** 
sacct -j 16333975 --format=jobid,jobname,submit,start,end,timelimit,elapsed

**\# show memory information ** 
sacct -j 16333975 --format=jobid%20,jobname%20,ReqMem,MaxRSS%20





**Show node specs for the "CPU" systems** 
sinfo -p cpu -N -o "%8N %5c %10m %10f %60G" \| column -t





**Show node specs for the "GPU" systems** 
sinfo -p gpu -N -o "%8N %5c %10m %10f %60G" \| column -t





**Don't use :** 
rm \* 
*or* 
rm -rf \*





**/data/isi**  is only available on **hpct04** and **hpct05**





**User and group statistics** are on 2 websites

<a href="https://hpcstats.op.umcutrecht.nl%20" rel="noopener noreferrer" target="_blank"><strong>hpcstats</strong> </a> 
With information about the old slurm setup.

<a href="https://hpcstats-new.op.umcutrecht.nl%20" rel="noopener noreferrer" target="_blank"><strong>hpcstats-new</strong> </a> 
With information about the new slurm setup \> 2023-01-01 

*\*available after log in on the network of your Institute*





**Slurm Nvidia-GPU Information** 
nvidia-smi 
nvidia-smi -L 
nvidia-smi -q

## How-To Guides

> **Summary:** Comprehensive task recipes: sbatch job submission, array jobs (--array), srun interactive sessions, MPI setup (module load openmpi, mpicc, mpirun -np), GPU access (-p gpu --gpus-per-node), R/Matlab/Bioperl setup, SSH proxy configs, debugging tips (strace, bash -x).

### How submit jobs

A job can be submitted in several ways. In the following, we illustrate some possibilities. 

### Using a shell script

Typically a job is submitted to the cluster by executing a shell script. For example: 
sbatch script.sh

with **script.sh** as:



\#!/bin/bash 
sleep 100 
echo \$SHELL 
/do/some/magic



The sbatch command has many available options. Type 
**man sbatch** 
for the full documentation.

An example containing some useful ones is shown here:

sbatch --mail-type=END,FAIL --mail-user=you@some.where.com script.sh

These (and any other) sbatch options can also be embedded in the submitted script-file. If shell.sh contains the following:



\#!/bin/bash 
\#SBATCH --time=00:10:00 
\#SBATCH --mem=5G 
\#SBATCH --mail-type=all 
\#SBATCH --mail-user=you@some.where.com 
\#SBATCH --error=slurm-%j.err 
\#SBATCH --output=slurm-%j.out

sleep 100

echo \$SHELL



then executing sbatch **script.sh** will automatically process all these embedded options.

### Using the wrap option

  
For quick one-off commands where no shell script is needed, you can also make use of the wrap option:



sbatch --job-name="zzz" --wrap="sleep 60"



### Using an Array Job

Array jobs are sets of (almost) identical jobs that are submitted as one. Submitting one array job generates less load on the HPC master, and allows you to limit the number of concurrently running jobs.

Given this script (pi.sh):



\#!/bin/bash 
if \[ -z "\$SLURM_ARRAY_TASK_ID" \]; then 
  scale=100 
else 
  scale=\$SLURM_ARRAY_TASK_ID 
fi

export BC_LINE_LENGTH=0

echo "scale=\$scale; a(1)\*4" \| bc -l



If I submit this script like:



sbatch --array=10-100:10%2



Then this will create a so-called "Array Job"; a set of identical tasks, differing only in the "task id". Specifying the "%2" option limits the maximum number of concurrently running jobs (to two). In this case, this will create approximations of PI, with 10, 20, 30, ... 100 decimals. The magic is of course in the SLURM_ARRAY_TASK_ID environment variable (automagically set by the cluster software), and the --array commandline option. Just submitting the script without -t option will cause SLURM_ARRAY_TASK_ID to be empty.

### Run a job after your other jobs have finished

If you want to submit a job that has to e.g. summarize the results of other jobs, and therefore has to wait until these other jobs are finished, one possibility is as follows. Submit the initial batch of jobs with a name that identifies them as one coherent set of jobs (here myjobset) :



for i in {1..10}; do 
  sbatch --job-name=zzz script.sh 
done



**sbatch --dependency=singleton --job-name=zzz --wrap="echo all done"**

This final job will remain in a "hold" state until all other jobs with the name "zzz" have finished; after that, it will automagically start. 
Please see **"man sbatch"** you can specify dependencies on many conditions.

## Using multiple CPU's in one job

First, some terminology. 
Most of our compute nodes have 2 physical CPU's. These are the items you can hold in your hand and install in a motherboard socket. 
These physical CPU's consist of multiple CPU "cores". These are mostly independent units, equivalent to what (in the old days...) you would actually call "a CPU". 
These CPU cores present themselves to the operating system as two, so that they can run two software threads at a time. This is called hyperthreading.

Unfortunately (in my opinion), these "hyperthreads" is what Slurm actually calls a "CPU". If you specify "srun --cpus-per-task=2", you will get 2 hyperthreads, which is just 1 CPU "core". In addition, if you request an odd number of "CPU's", you will get an even number, rounded up. So: "--cpus-per-task=3" will get you 4 hyperthreads (2 CPU cores).

The short summary if you come from SGE: qsub -pe threaded N is equivalent to sbatch --cpus-per-task 2N. 
That's it, read no further.

Still here? The real beauty is that you can also request multiple "tasks", or multiple "nodes". And then "tasks per node", or "CPU's per GPU", or "memory per GPU", 
and of course still "CPU's per task". 
And then the outcome also depends on whether you used **"sbatch"** or **"srun"**.

For inspiration, read this page :    [https://slurm.schedmd.com/cpu_management.html](https://slurm.schedmd.com/cpu_management.html) 
The possibilities (and potential confusion) are endless. 
(I told you to stop reading at "that's it"...)

### Using a GPU

Something like: 
srun -p gpu -c 2 --gres=tmpspace:10G --gpus-per-node=1 --time 24:00:00 --mem 100G --pty bash 
will give you an interactive session with 1 GPU.

srun -p gpu --gpus-per-node=quadro_rtx_6000:1 --pty bash 
or 
srun -p gpu --gpus-per-node=2g.20gb:1 --pty bash

will request a specific type of GPU. Currently we have "Quadro RTX 6000", "TeslaV100", "TeslaP100" and "NVIDIA A100" GPU-card available. 
see :   [All Available GPU cards ](#gpu-nodes)

### 

### Cuda software

is installed on all the GPU servers (sinfo -p gpu) in /usr/local : 
**\$ ls -al /usr/local/ \| grep cuda**

 lrwxrwxrwx. 1 root root 9 Jul 27 2021 cuda -> cuda-10.2
 drwxr-xr-x. 15 root root 265 Jun 23 2021 cuda-10.1
 drwxr-xr-x. 16 root root 278 Jul 27 2021 cuda-10.2
 lrwxrwxrwx. 1 root root 25 Jun 24 2021 cuda-11 -> /etc/alternatives/cuda-11
 drwxr-xr-x. 15 root root 4096 Jun 24 2021 cuda-11.3
 drwxr-xr-x. 15 root root 265 Jun 23 2021 cuda-9.1

### How to see which jobs are currently submitted and/or running on the HPC cluster ?

Simply type **squeue** and an overview will be shown or 



squeue -u yourusername



will show only your own jobs.

### Memory and Java

Please note that for java jobs, the -Xmx parameter for configuring the java memory allocation space (or java heapspace) does not correspond to the total memory used by the java virtual machine. Besides the heapspace, there is also room needed for the garbage collector and other processes running within java. To make sure the java process can run, make sure you keep a safe margin between the value specified with the -Xmx parameter and your requested memory (-l h_vmem=whatever). We recommend keeping at least 3GB available. SLURM seems to be more reasonable in this respect than SGE; you could try a smaller margin.

### How to use the HPC cluster in an interactive fashion

Use the srun command, like this:



srun --pty bash



If you are going to use graphical programs:



srun --x11 --pty bash



## How to log in from outside the UMC network

The HPC cluster can be reached from outside the UMC network by first connecting to an SSH gateway, 
from which you can log in to the login/submission servers hpcs05 and hpcs06. 
You can connect to the SSH gateway as described [here](#login-overview).

## Simplifying access using the SSH gateway as a proxy

To simplify the process, you can also specify that ssh should use the gateway as a proxy when connecting to hpcs05 or hpcs06. 
This way you don't have to manually type in the second ssh command to connect to hpcs05 or hpcs06. 
In combination with an ssh-agent, you also don't have to type in your passphrase for the certificate.

### Linux / MacOSX

Edit (or create) the .ssh/config file and add a host entry:





\# usage : ssh hpcgw 
Host hpcgw 
  HostName hpcgw.op.umcutrecht.nl 
  User myusername 
  IdentityFile ~/.ssh/id_ed25519_hpc 

\# usage : ssh gw2hpcs05 
Host gw2hpcs05 
  HostName hpcs05.op.umcutrecht.nl 
  User myusername 
  ProxyJump hpcgw

This now has created an alias gwhpcs05 that uses the gateway as a proxy. From now on you can type

 ssh gwhpcs05

and the system will automatically use the gateway as a proxy to connect to hpcs05. You can also use scp to copy data, like:

 scp -r yourdirectory gwhpcs05:/hpc/shared/some/where

or

 cp ./myfile.txt gwhpcs05:/home/mygroup/myusername/tmp

If you also don't want to type in the passphrase, you'll also need an ssh-agent. Normally, your desktop will handle this for you transparantly. For KDE environments, you can add the following to your .xsession file:



ssh-agent \> \$HOME/.ssh/current_agent.sh 
. \$HOME/.ssh/current_agent.sh

ssh-add 
startkde

\# when exiting, kill agent 
ssh-agent -k



This will automatically startup the ssh-agent when logging into your machine locally and ask for the passphrase. After this, the ssh-agent takes care of providing the right key and authentication.

## Using graphics on your local workstation

Requirements is an X server on your local machine. 
For Apple/Linux it is standard available. For Windows you can use WSL with X-server installed, Xming, Exceed, or the built in X server of [MobaXterm](#login-with-mobaxterm)

create a stanza in your ~/.ssh/config like :



Host hpcgw 
  HostName hpcgw.op.umcutrecht.nl 
  User myusername 
  IdentityFile ~/.ssh/id_ed25519_hpc

Host gwhpcs05X 
  HostName hpcs05.op.umcutrecht.nl 
  User myusername 
  ForwardX11 yes 
  Compression yes 
  Proxyjump hpcgw



Then setup the ssh tunnel by :



ssh gwhpcs05X



**login on the gateway with passphrase**

then

log into the hpcs05 with your **password**

**Now you're on hpcs05**

Then jump to a compute-node by : 
(for not running your code on the submit host) 
srun \<parameters cores and time and tmp\> --x11 --pty bash

And start whatever your graphical program is (maybe it is slow but for small programs it's useful).

## How to connect from Windows

If you are normally working with Windows you can use the built in ssh client from the Powershel terminal. In case you prefer a client with a graphical user interface, we recommend you to have a look at the software [MobaXterm](#login-with-mobaxterm). 
It is very user-friendly and also allows you to copy files between Windows and the HPC cluster.

## Multithreading in R

There are a number of packages available for parallelization. Sometimes, it is even just individual functions that can make use of the parallel environment. In this case, it is important that you reserve the appropriate number of slots to be used. You can do this as follows.

First, submit your job and reserve the slots you would like to use:



sbatch -c 6 --wrap="R --vanilla \< script.R"



Second, retrieve the number of reserved slots in your R script by:



nslots \<- Sys.getenv( "SLURM_CPUS_ON_NODE" ) 
print( nslots ) 
some.parallel.function( slots = nslots )



This assures that the appropriate number of slots is always reserved for you.

## How to limit Java's garbage collection to the correct number of slots

Quote ( [https://blog.codecentric.de/en/2013/01/useful-jvm-flags-part-6-throughput-collector/](https://blog.codecentric.de/en/2013/01/useful-jvm-flags-part-6-throughput-collector/)  ):

"**With -XX:ParallelGCThreads=** we can specify the number of GC threads to use for parallel GC.

For example, with **-XX:ParallelGCThreads=6** each parallel GC will be executed with six threads. 
If we don’t explicitly set this flag, the JVM will use a default value which is computed based on the number of available (virtual) processors. 
The determining factor is the value N returned by the Java method Runtime.availableProcessors(). 
For N \<= 8 parallel GC will use just as many, i.e., N GC threads. For N \> 8 available processors, the number of GC threads will be computed as 3+5N/8. 
Using the default setting makes most sense when the JVM uses the system and its processors exclusively. 
However, if more than one JVM (or other CPU-hungry systems) are all running on the same machine, we should use -XX:ParallelGCThreads in order to reduce the number of GC threads to an adequate value. 
For example, if four server JVMs are running on a machine with 16 processor cores, then -XX:ParallelGCThreads=4 is a sensible choice so that GCs of different JVMs don’t interfere with each other." 
In our case, please set -XX:ParallelGCThreads to the environment variable SLURM_CPUS_ON_NODE.

## How to use MPI

IN NEED OF REVISION

OpenMPI is installed on all nodes. However, before using it, you'll have to issue **module load openmpi** to use the included utilities. 
You'll have to use -pe mpi \#slots to be able to use it.

An example:

Given this program (mpihello.c):



\#include \<stdio.h\> 
\#include \<mpi.h\>

int main(int argc, char \*argv\[\]) { 
   int numprocs, rank, namelen; 
   char processor_name\[MPI_MAX_PROCESSOR_NAME\];

   MPI_Init(&argc, &argv); 
   MPI_Comm_size(MPI_COMM_WORLD, &numprocs); 
   MPI_Comm_rank(MPI_COMM_WORLD, &rank); 
   MPI_Get_processor_name(processor_name, &namelen);

   printf("Process %d on %s out of %d\n", rank, processor_name, numprocs);

   MPI_Finalize(); 
} 



Compile this with:

 module load openmpi
 mpicc mpihello.c -o mpihello 

Use this script (mpihello.sh) to submit it (including the required SGE options):



\#!/bin/bash 
\#\$ -S /bin/bash 
\#\$ -q all.q 
\#\$ -pe mpi 3 
\#\$ -R y 
\#\$ -cwd 
\#\$ -M youremailaddress@umcutrecht.nl 
\#\$ -m as



**module load openmpi** 
**mpirun -np 3 /path/to/mpihello**

The submit command: **qsub mpihello.sh**

This will eventually produce an output file (mpihello.sh.o9543479, or something like it), containing something like:

 Starting: 1 on hpcn051.op.umcutrecht.nl out of 3
 Starting: 2 on hpcn042.op.umcutrecht.nl out of 3
 Starting: 0 on hpcn052.op.umcutrecht.nl out of 3

And some ugly (but harmless) messages in the error file (mpihello.sh.e9543479):

 bash: module: line 1: syntax error: unexpected end of file
 bash: error importing function definition for `module'
 bash: module: line 1: syntax error: unexpected end of file
 bash: error importing function definition for `module'

When adapting the submit script to your needs, be sure to match up the numbers in "-pe mpi 3" and "mpirun -np 3".

## Debugging tips

**Be as verbose as possible**

A useful trick if you're using bash is to use the -x option, either by writing



\#!/bin/bash -x



as the first line of the script, or by specifying

**set -x**

somewhere in your script. It will show you all the substitutions done inside the script prior to executing them. This allows you to spot e.g. missing values for shell variables

## Obscure error messages

They sometimes relate to files that can not be found. If the program is a binary program (i.e. compiled from C or so), it may help to run the program under the Unix utility strace. This logs each and every kernel call, most importantly the opening of files (and directories) and network connections. Run it as



strace -o strace.out theprogram -with all -the -necessary options 



and scour the **strace.out** file for what the program actually tries to open.

## First make it work interactively

It's best to do this on one of the compute nodes. You can login to one using srun --pty bash. The queueing system randomly picks an available node and sends you there. The environment and, importantly, the set of disks that are visible is identical to that of the batch jobs. To close your session, simply type exit.

## Make it work on a small subset first

Sounds obvious, but in practice, the urge to immediately submit all 20000 jobs (and see all of them fail) is stronger... 🙂

## Save the intermediate state of a job

This may not always be possible, or too much work, but if you're jobs are long-running (more than a few hours), it may pay to save intermediate results so that you can resume failed jobs.

## Install error handlers so you can do post-mortem debugging

For C-like programs for which you have source code, you can do post-mortem debugging on the core file that is produced upon failure. To arrange this, do



ulimit -c unlimited



prior to running the binary. The core file can be inspected inside the debugger, and maybe data can be salvaged.

In R, you can install an error handler using



options(error=some.function, show.error.messages=TRUE)



where some.function is an R function that you have to define. One of the things this function could do 
is e.g. save(file=sprintf("~/tmp/Crashdata-%s.rda", Sys.getenv("JOB_ID")), data1, data2, data3). 
(Note the use of environment variable \$JOB_ID to make the dump file unique; see below). 
If things crash, you can still recover them from the crash file. Another thing to save is the stack trace, which can help you pinpoint where an error occurred. 
For this, do something like dump.frames(dumpto=sprintf("~/tmp/Stacktrace-%s", Sys.getenv("JOB_ID")), to.file=TRUE). 
This dump can be inspected in an interactive session using debugger().

## Matlab

It is possible to use matlab on the HPC, with some limitations.

1. Compile matlab code as standalone executables with a linux distribution of matlab on your local workstation (linux only). 
 or 
 Download and install the linux version of [Matlab](https://nl.mathworks.com/downloads/downloads) 
 in your group directory /hpc/local/Rocky8/\<mygroup\>/MATLAB 
 (for employes of the Utrecht University there is a free available campuslicense see : [intranet.uu.nl](https://intranet.uu.nl/matlab) 
 Then compile your matlab code as standalone binary by starting a qlogin session

ssh gateway or direct to hpcsubmit

Use "**srun --pty bash**" to get a shell 
**matlab** 
or 
**activate_matlab.sh** (because every compute-node must have a valid license) 
And create your matlab binary.

1. use the MATLAB RUNTIME by module load mcr/v94 in your bash-script job to run your matlab-binary
2. execute your bash script with sbatch.

- this is the content of the matlab file hello.m 
 disp('Hello world')



- create a binary file 
 mcc -m hello.m



- create a shell-script (t1.sh) to run this matlab binary 
 \#!/bin/bash 
 module load mcr/v94 (R2018a) 
 \<mypath\>hello



- excute in the HPC 
 sbatch t1.sh

You can update the matlab license by starting the license update script : 
/hpc/local/Rocky8/\<mygroup\>/MATLAB/R2018a/bin/activate_matlab.sh 
Login with your matlab credentials and the license is added in /hpc/local/Rocky8/\<mygroup\>/MATLAB/R2017a/licenses 
for this host.

R & Rstudio

Rstudio Server is available through the [Ondemand webportal](#open-ondemand). Alternatively, you can use R (command line version) and RStudio Desktop (Graphical R shell from within the Open OnDemand Desktop app) on the HPC, but you have to set it up your self. This way you can control which versions are used so that you have the compatible library folders as well.

**To setup R: **

Download the R version as tar ball from (example) in the location you want to install it (not your home folder!): [Index of /src/base/R-4 (r-project.org)](https://cran.r-project.org/src/base/R-4/)

On the command line execute: tar -xzf the downloaded R tarball (ie R-4.3.2.tar.gz)

Enter the new folder: cd R-4.3.2

execute: ./configure --prefix=\$PWD --enable-R-shlib

execute: make -j 4

execute: make install

execute: ln -s -full location path-/R-4.3.2/bin/R ~/bin/R

Now you can start R by just typing 'R' (without quotes) on the command line.

**To setup Rstudio:**

Download the version of Rstudio you prefer as Tarball for RedHat/Fedora (Currently the HPC uses version 8) in the location you want to install it (not your home folder!) from here : [RStudio Desktop - Posit](https://posit.co/download/rstudio-desktop/)

On the command line execute: tar -xzf the downloaded RStudio tarball (ie RSTUDIO-2023.12.0-369-X86_64-FEDORA.TAR.GZ)

execute: ln -s -full location path-/rstudiofolder/rstudio ~/bin/rstudio

To run rstudio, go to openondemand and start a desktop session. Once this is started, open a terminal and type 'rstudio' (without quotes).

## Bioperl

Bioperl is default not installed on the HPC . 
Use this bullit-list to install



1. wget -O- [https://cpanmin.us](http://cpanmin.us) \| perl - -l ~/perl5 App::cpanminus local::lib
2. eval \`perl -I ~/perl5/lib/perl5 -Mlocal::lib\`
3. echo 'eval \`perl -I ~/perl5/lib/perl5 -Mlocal::lib\`' \>\> ~/.profile
4. echo 'export MANPATH=\$HOME/perl5/man:\$MANPATH' \>\> ~/.profile



\# logout and login again to activate your new environment-settings.



1. cpanm Module::Build



\# Install Bioperl by:



1. cpanm install CJFIELDS/BioPerl-1.6.924.tar.gz


---

# Login & Access

## Login Overview

> **Summary:** Entry point for all login methods. Links to OS-specific guides. Use when user asks 'how do I connect' without specifying OS.

How to get acces to the HPC depends on the OS and the Location of your workstation 
but you always need a ssh-client on your workstation.

## From outside the UMC network

1. create public/secret ssh-key pair with a secure *selfmade* **passphrase**
2. send the public key to <hpcsupport@umcutrecht.nl>
3. log in into the gateway with the key *(with your passphrase)*
4. log into the submit or transfer node 
 ssh hpcs05 
 or  ssh hpcs06 
 or  ssh hpct04 
 or  ssh hpct05

**Windows-users** can use the[ PowerShell ](#login-with-powershell)terminal or [configure](#login-from-windows) the free  [MobaXterm](#login-from-windows) or [Putty](#login-from-windows) software to access the gateway.

**Linux or Mac users **can use the command line to [configure](#login-from-linux-mac) ssh .

## From inside the UMC network

If you work from the inside of the UMC Network or other trusted networks you can direct access the HPC

**ssh hpcs05.op.umcutrecht.nl** 
     or 
**ssh hpcs06.op.umcutrecht.nl** 
     or 
**ssh hpct04.op.umcutrecht.nl** 
     or 
**ssh hpct05.op.umcutrecht.nl**

## Login from Linux / Mac

> **Summary:** Native SSH client usage: ssh-keygen -t ed25519, ssh-copy-id, ~/.ssh/config ProxyJump setup for gateway access. Covers internal (direct) and external (via hpcgw.op.umcutrecht.nl) connections.

All you need is to send us (hpcsupport@umcutrecht.nl) your SSH public key.

Perform the following steps on your own (or some other trusted) machine:



mkdir ~/.ssh   \# May not be necessary; you probably have this directory already. 
cd ~/.ssh 
ssh-keygen -t ed25519 -C "HPC" -f ~/.ssh/id_ed25519_hpc



When prompted,  enter a strong, secure **passphrase**.

This will create two files: 
**id_ed25519_hpc**, 
and 
**id_ed25519_hpc.pub**.

Please mail  the **id_ed25519_hpc.pub** file to [hpcsupport@umcutrecht.nl](mailto:mailto:hpcsupport@umcutrecht.nl)

We configure your public-key on the gateway and you will be able to log into the gateway by :

> **Note:**
> ssh -i ~/.ssh/id_ed25519_hpc -l *myusername* hpcgw.op.umcutrecht.nl

Login with your selfmade "passphrase" .

Next step is goto the HPC by :

> **Note:**
> ssh hpcs05 
> or 
> ssh hpcs06 
> or 
> ssh hpcsubmit

and login with your "password" .

You can automate this procedure by creating as ssh-config file. It should be located in your ".ssh" directory, and be called "config". 
This is an example. 
Copy and save this file in the **.ssh** directory and name it **config**.

**Replace "wvanburen" with your own "username".**

 #############################################
 # file : ~/.ssh/config
 # date : 20260129
 # expl : default ssh config file example 
 #############################################

 # usage : ssh hpcgw
 Host hpcgw
 HostName hpcgw.op.umcutrecht.nl
 User wvanburen
 IdentityFile ~/.ssh/id_ed25519_hpc

 # usage : ssh gw2hpcs05
 Host gw2hpcs05
 HostName hpcs05.op.umcutrecht.nl
 User wvanburen
 ProxyJump hpcgw

 # usage : ssh gw2hpcs06
 Host gw2hpcs06
 HostName hpcs06.op.umcutrecht.nl
 User wvanburen
   ProxyJump hpcgw

 # usage : ssh gw2hpcs05X
 Host gw2hpcs05X
 HostName hpcs05.op.umcutrecht.nl
 User wvanburen
 ForwardX11 yes
   ProxyJump hpcgw

 # usage : ssh gw2hpct04
 Host gw2hpct04
 HostName hpct04.op.umcutrecht.nl
   User wvanburen
   ProxyJump hpcgw

 # usage : ssh gw2hpct05
 Host gw2hpct05
 HostName hpct05.op.umcutrecht.nl
 User wvanburen
   ProxyJump hpcgw

 # usage : ssh hpcs05
 Host hpcs05
 HostName hpcs05.op.umcutrecht.nl
 User wvanburen

 # usage : ssh hpcs05X
 Host hpcs05X
 HostName hpcs05.op.umcutrecht.nl
 User wvanburen
 ForwardX11 yes

 # usage : ssh hpcs06
 Host hpcs06
 HostName hpcs06.op.umcutrecht.nl
 User wvanburen

 # usage : ssh hpcs06X
 Host hpcs06X
 HostName hpcs06.op.umcutrecht.nl
 User wvanburen
 ForwardX11 yes

 # usage : ssh hpct04
 Host hpct04
 HostName hpct04.op.umcutrecht.nl
 User wvanburen

 # usage : ssh hpct05
 Host hpct05
 HostName hpct05.op.umcutrecht.nl
 User wvanburen

 # usage : ssh ft_gw2hpct04
 # then start a filezilla session on localhost to port 8888
 # for filetransfer from hpct04 to local machine
 Host ft_gw2hpct04
 HostName hpct04.op.umcutrecht.nl
 User wvanburen
 LocalForward 8888 hpct04.op.umcutrecht.nl:22
   ProxyJump hpcgw

 # usage : ssh ft_gw2hpct05
 # then start a filezilla session on localhost to port 8888
 # for filetransfer from hpct05 to local machine
 Host ft_gw2hpct05
 HostName hpct05.op.umcutrecht.nl
 User wvanburen
 LocalForward 8888 hpct04.op.umcutrecht.nl:22
   ProxyJump hpcgw
 #########################################

With this oneliner you can replace **wvanburen** into your own **username**  in the file **"~/.ssh/config"**



sed -i 's/wvanburen/myusername/' ~/.ssh/config



for **Mac** users



sed -i '' 's/wvanburen/myusername/' ~/.ssh/config"



and Try



ssh gw2hpcs05



It will ask for your **passphrase** on the gateway hpcgw followed by your hpc-**password** on hpcs05 .

## Login from Windows

> **Summary:** Windows SSH options overview: native PowerShell ssh, PuTTY, MobaXterm. Key generation with ssh-keygen, external access requirements.

This is a topic that generates a lot of e-mail. 
Please have a look at the step-by-step configuration of the most-used ssh clients:

- [MobaXterm](#login-with-mobaxterm)
- [Powershell Terminal](#login-with-powershell)
- [Putty](#login-with-putty)

Please be very careful that you use the correct username (not your e-mail address, no dots, all lowercase letters/numbers) and the correct ssh-key.

If you connect through the gateway, and you get blocked, include your IP address in your e-mail: [https://www.whatismyip.com/](https://www.whatismyip.com/)

## Login with PuTTY

> **Summary:** PuTTY configuration: Session setup for hpcs05/hpcs06, Connection>Data username, puttygen key generation (ED25519), Pageant key agent, tunneling for gateway access.

Download the Putty software  :   [Putty-ssh client](https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html)  

Put in a directory on your local machine p.e c:\users\wvanburen\putty 
unzip the zip file



Create a public key by executing \*puttygen.exe\*.



![1770991799904-453.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770991799904-453.png)



Enter 2 times a selfmade password called "passphrase" .



![1770991904523-212.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770991904523-212.png)



Copy and paste the public-key and mail to <hpcsupport@umcutrecht.nl>.



![1770991963514-333.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770991963514-333.png)



Save your private key.



![1770992103535-840.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770992103535-840.png)

![1770992060362-334.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770992060362-334.png)



Create and save a configuration to hpcgw.op.umcutrecht.nl named hpcgw.



![putty6.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/putty6.png)



Add you private key to the configuration.



![1770992317859-508.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/1770992317859-508.png)



And save it into the configuration.



![putty8.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/putty8.png)



Run the config and enter your selfmade passphrase.



![putty9.png](../../../../../../attachment/xwiki/Main/Login/Windows/Putty/WebHome/putty9.png)

## Login with MobaXterm

> **Summary:** MobaXterm setup: Session creation, built-in X11 forwarding, SFTP file browser, key generation via Tools>MobaKeyGen, gateway tunneling configuration.

To use the HPC you must use a ssh-client. 
An example of this software is the Mobaxterm for Windows.(<https://mobaxterm.mobatek.net/>)

To access the HPC from outside the UMC network you have to use the gateway first. 
Therefore you have to create a secret and public key combination.

Use these steps to configure the software :



**Create a Secret Key**



![moba1.jpg](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/moba1.jpg)



**Select EdDSA under paramters and click on Generate and start moving your mouse in the "No key" field**



![1770989382287-699.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/1770989382287-699.png)



**Enter a selfmade password called "passphrase" in the fields highlighted below** 
and store this password into your password manager because you need this later on.



![1770989687381-259.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/1770989687381-259.png)



**Save you key somewhere on your local filesystem\* and don't replace it afterwards because you can not login anymore.**



![1770991038420-696.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/1770991038420-696.png)



**Copy and paste your public-key and mail this to <hpcsupport@umcutrecht.nl>**



![1770990492304-717.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/1770990492304-717.png)



**Now create a ssh session**



![moba6.jpg](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/moba6.jpg)



**Fill in this form and tab like this 
Remote host = hpcs05.op.umcutrecht.nl and your username**

***If you want to connect from outside also set this:* 
Click on SSH gateway and fill define gateway SSH server = hpcgw.op.umcutrecht.nl, set your username and select the private key file you saved before.**



![1770991374896-449.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/1770991374896-449.png)



**Ok and save the session.**



![image-20231103144150-2.png](../../../../../../attachment/xwiki/Main/Login/Windows/MobaXterm/WebHome/image-20231103144150-2.png)



Double click on the saved session to make a connection.

## Login with PowerShell

> **Summary:** Windows native SSH: ssh-keygen in PowerShell, .ssh folder setup, config file for ProxyJump through gateway, ssh-agent service configuration.

All you need is to send us (hpcsupport@umcutrecht.nl) your SSH public key.

Perform the following steps on your own (or some other trusted) machine:



mkdir ~/.ssh   \# May not be necessary; you probably have this directory already. 
cd ~/.ssh 
ssh-keygen -t ed25519 -C HPC -f id_ed25519_hpc



When prompted,  enter a strong, secure **passphrase**.

This will create two files: 
**id_ed25519_hpc**, 
and 
**id_ed25519_hpc.pub**.

Please mail  the **id_ed25519_hpc.pub** file to [hpcsupport@umcutrecht.nl](mailto:mailto:hpcsupport@umcutrecht.nl)

We will configure your public-key on the gateway and after that you can log into the gateway by :

> **Note:**
> ssh -i ~/.ssh/id_ed25519_hpc -l *myusername* hpcgw.op.umcutrecht.nl

Login with your selfmade "passphrase" .

Next step is goto one of the HPC submit node by :

> **Note:**
> ssh hpcs05 
> or 
> ssh hpcs06 
> or 
> ssh hpcsubmit

and login with your "password" .

You can automate this procedure by creating as ssh-config file. It should be located in your ".ssh" directory, and be called "config". 

You can create the file also from the powershell terminal by typing

> **Note:**
> cd ~/.ssh
> notepad 'config.'

Below is an example. 
Copy and save this file in the **.ssh** directory and name it **config**.

**Replace (Ctrl-H in notepad) "wvanburen" with your own "username". **

 #############################################
 # file : ~/.ssh/config
 # date : 20260129
 # expl : default ssh config file example 
 #############################################

 # usage : ssh hpcgw
 Host hpcgw
   HostName hpcgw.op.umcutrecht.nl
   User wvanburen
   IdentityFile ~/.ssh/id_ed25519_hpc

 # usage : ssh gw2hpcs05
 Host gw2hpcs05
   HostName hpcs05.op.umcutrecht.nl
   User wvanburen
   ProxyJump hpcgw

 # usage : ssh gw2hpcs06
 Host gw2hpcs06
   HostName hpcs06.op.umcutrecht.nl
   User wvanburen
   ProxyJump hpcgw

 # usage : ssh gw2hpcs05X
 Host gw2hpcs05X
   HostName hpcs05.op.umcutrecht.nl
   User wvanburen
   ForwardX11 yes
   ProxyJump hpcgw

 # usage : ssh gw2hpct04
 Host gw2hpct04
   HostName hpct04.op.umcutrecht.nl
   User wvanburen
   ProxyJump hpcgw

 # usage : ssh gw2hpct05
 Host gw2hpct05
   HostName hpct05.op.umcutrecht.nl
   User wvanburen
   ProxyJump hpcgw

 # usage : ssh hpcs05
 Host hpcs05
   HostName hpcs05.op.umcutrecht.nl
   User wvanburen

 # usage : ssh hpcs05X
 Host hpcs05X
   HostName hpcs05.op.umcutrecht.nl
   User wvanburen
   ForwardX11 yes

 # usage : ssh hpcs06
 Host hpcs06
   HostName hpcs06.op.umcutrecht.nl
   User wvanburen

 # usage : ssh hpcs06X
 Host hpcs06X
   HostName hpcs06.op.umcutrecht.nl
   User wvanburen
   ForwardX11 yes

 # usage : ssh hpct04
 Host hpct04
   HostName hpct04.op.umcutrecht.nl
   User wvanburen

 # usage : ssh hpct05
 Host hpct05
   HostName hpct05.op.umcutrecht.nl
   User wvanburen

 # usage : ssh ft_gw2hpct04
 # then start a filezilla session on localhost to port 8888
 # for filetransfer from hpct04 to local machine
 Host ft_gw2hpct04
   HostName hpct04.op.umcutrecht.nl
   User wvanburen
   LocalForward 8888 hpct04.op.umcutrecht.nl:22
   ProxyJump hpcgw

 # usage : ssh ft_gw2hpct05
 # then start a filezilla session on localhost to port 8888
 # for filetransfer from hpct05 to local machine
 Host ft_gw2hpct05
   HostName hpct05.op.umcutrecht.nl
   User wvanburen
   LocalForward 8888 hpct04.op.umcutrecht.nl:22
   ProxyJump hpcgw
 #########################################

After editing and saving the file you can connect to the **hpcs05 submit server **from the Powershell terminal with the following command.



ssh gw2hpcs05



It will ask for your **passphrase** on the gateway hpcgw followed by your hpc-**password** on hpcs05 .


---

# SLURM Job Scheduler

## SLURM Guide

> **Summary:** Complete SLURM reference: srun (interactive), sbatch (batch), salloc (allocation). Partitions: cpu (default), gpu. Resource flags: --mem, --time, -c (cpus), --gres=tmpspace:NNG, --gpus-per-node. GPU types: quadro_rtx_6000, tesla_v100, tesla_p100, a100. SGE migration table (qsub→sbatch, qstat→squeue, qdel→scancel). Resource limits per account group via showuserlimits. $TMPDIR=/scratch/$SLURM_JOB_ID for local scratch.

![image](https://slurm.schedmd.com/slurm_logo.png)

Starting in May 2019, we're testing our new Slurm setup. [Slurm](https://slurm.schedmd.com/) is similar to SGE  ; it manages a cluster, distributing user jobs in (hopefully) a fair and efficient way.

The concepts are comparable, but the syntax is not.

This page will hopefully grow organically. Feel free to make corrections and add your tips, tricks and insights.

## Defaults

Some defaults:

> **Note:**
> - There are two "partitions" (like a "queue" in SGE ), called "cpu" (for normal jobs) and "gpu" (where some GPU's are available). The default is "cpu".
> - Default runtime is 10 minutes.
> - Default memory is 10 GB.
> - By default, your job gets 1 GB of "scratch" local disk space in "\$TMPDIR" (where TMPDIR=/scratch/\$SLURM_JOB_ID).

## Running jobs

You can run jobs using "**srun**" (interactively), "**sbatch**" (like qsub), or use "**salloc**" to allocate resources and then "**srun**" your commands in that allocation.

## srun

srun is mostly useful for testing, and for interactive use. It will execute the command given, and wait for it to finish. Some examples:

> **Note:**
> - srun sleep 60
> 
> - srun -c 4 bash -c "hostname; stress -c 10".    \# this will start 1 task, getting 4 cores (2 CPU's, 2 cores on each).

This is different from:

> **Note:**
> - srun -n 4 bash -c "hostname; stress -c 10".   \#This will start 4 seperate "tasks", each getting 1 CPU (2 cores on each). Eight threads in total.

The previous form (-c) is usually what you want. Just one "job" with 4 CPU cores.

To me, the number of tasks, CPU's and cores is sometimes slightly surprising. I guess it will make sense after a while...

You can also use srun to get an interactive shell on a compute node (like qlogin):

- srun -c 2 --mem 5G --time 01:00:00 --pty bash

Or on a specific node:

- srun -c 2 --mem 5G --time 01:00:00 --nodelist n0014 --pty bash

## sbatch

sbatch is like qsub. Commandline options are similar to srun, and can be embedded in a script file:

 #!/bin/bash
 #SBATCH -t 00:05:00
 #SBATCH --mem=20G
 #SBATCH -o log.out
 #SBATCH -e errlog.out
 #SBATCH --mail-type=FAIL
 #SBATCH --mail-user=youremail@some.where #Email to which notifications will be sent

 env
 echo "Hello World" 

### sbatch Force job to run on a compute node

 #SBATCH --nodelist=n0065 # force to run job on

## salloc/srun

Quoting from the documentation:

The final mode of operation is to create a resource allocation and spawn job steps within that allocation. The salloc command is used to create a resource allocation and typically start a shell within that allocation. One or more job steps would typically be executed within that allocation using the srun command to launch the tasks. Finally the shell created by salloc would be terminated using the exit command.

Be very careful to use srun to run the commands within your allocation. Otherwise, the commands will run on the machine that you're logged in on! See:

 # Allocate two compute nodes:
 [mvanburen@hpcs05 ~]$ salloc -N 2
 salloc: Pending job allocation 1635
 salloc: job 1635 queued and waiting for resources
 salloc: job 1635 has been allocated resources
 salloc: Granted job allocation 1635
 salloc: Waiting for resource configuration
 salloc: Nodes n[0009-0010] are ready for job

 # I got n0009 and n0010
 [mvanburen@hpcs05 ~]$ srun hostname
 n0009.compute.hpc
 n0010.compute.hpc

 # But this command just runs on the machine I started the salloc command from!
 [mmarinus@hpcs05 ~]$ hostname
 hpcm05.manage.hpc

 # Even if you "srun" something, be careful where (e.g.) variable expansion is done:
 [mmarinus@hpcs05 ~]$ srun echo "running on $(hostname)"
 running on hpcs05.manage.hpc
 running on hpcs05.manage.hpc

 # Exit the allocation
 [mvanburen@hpcs05 ~]$ exit
 exit
 salloc: Relinquishing job allocation 1635

## Local (scratch) disk space

If your job benefits from (faster) local disk space (like "qsub -l tmpspace=xxx"), local scratch is available in /scratch and by default a folder with 1 GB space is created in /scratch/\$SLURM_JOB_ID. This folder reference to with \$TMPDIR environment variable for each job. You can request more space if needed for a job like this:

srun --gres=tmpspace:10G --pty bash

Of course, this works for all the slurm commands. The scratch disk space will be made available in \$TMPDIR (/scratch/\$SLURM_JOB_ID) and will be erased automatically when your job is finished. Note: the "--tmp" option to srun/sbatch sounds like it will do the same, but it won't. Please use the "--gres" method.

PS: don't set your tmpspace \*too\* small or your job will fail. At least 200M should be fine.

## Using a GPU

Something like:

> **Tip:**
> srun -p gpu -c 2 --gres=tmpspace:10G --gpus-per-node=1 --time 24:00:00 --mem 100G --pty bash

will give you an interactive session with 1 GPU.

> **Tip:**
> srun -p gpu --gpus-per-node=quadro_rtx_6000:1 --pty bash

will request a specific type of GPU. Currently we have Tesla P100, Tesla V100, RTX6000, and A100 Nvidia [gpus available](#gpu-nodes).

## SGE versus SLURM

| | | |
|----|----|----|
| SGE | vs. | SLURM |
| qstat | \- | [squeue](https://slurm.schedmd.com/squeue.html) |
| qsub | \- | [sbatch](https://slurm.schedmd.com/sbatch.html) |
| qsub -P foo 1.sh | \- | sbatch -A foo 1.sh |
| qsub -l h_vmem=20G 1.sh | \- | sbatch --mem 20G 1.sh |
| qsub -l tmpspace=100G a1.sh | \- | sbatch --gres=tmpspace:100G a1.sh |
| qsub -l h_rt=10:00:00 a1.sh | \- | sbatch --time=10:00:00 a1.sh |
| qdel | \- | [scancel](https://slurm.schedmd.com/scancel.html) |
| qlogin | \- | [srun --pty bash](https://slurm.schedmd.com/srun.html) |
| \#\$ -pe threaded 2 | \- | \#sbatch -c 4 |

examples : 
*submit job named 1.sh* 
**sge** = qsub 1.sh 
= 
**slurm** = sbatch 1.sh

# Resource Limits in Slurm

The resources that we put limits on are: CPU, memory, GPU. And runtime, sort of.

Whom do we limit this to? Not to you, as an individual, but to all the people in your HPC group (your "account") together. Your job can be pending because your colleague is using all your group's resources.

There are two types of limits: just a number (your jobs can not use more than X CPU's simultaneously, no more than Y GPU's and no more than Z gigabytes of memory); and a number times the requested runtime. That last one is always tricky to explain properly; we'll get to that.

## The boring stuff that's good to know

A word of terminology: in the commands to come, you will often see the terms "TRES" and "GRES". A TRES is a "trackable resource": something that you can request and that we can put limits on. To reiterate, we limit the use of: CPU's, memory and GPU's. A GRES (generic resource) is just a TRES that doesn't have its own category yet (GPU is actually a GRES). For our purposes, GRES and TRES are just the same thing.

Another thing that may be good to point out again (copy/pasted from the [HowToS](https://wiki.bioinformatics.umcutrecht.nl/bin/view/HPC/HowToS) page...):

Most of our compute nodes have 2 physical CPU's. These are the items you can hold in your hand and install in a motherboard socket.

These physical CPU's consist of multiple CPU "cores". These are mostly independent units, equivalent to what (in the old days...) you would actually call "a CPU".

These CPU cores present themselves to the operating system as two, so that they can run two software threads at a time. This is called hyperthreading.

Unfortunately (in my opinion), these "hyperthreads" is what Slurm actually calls a "CPU". If you specify "srun --cpus-per-task=2", you will get 2 hyperthreads, which is just 1 CPU "core". In addition, if you request an odd number of "CPU's", you will get an even number, rounded up. So: "--cpus-per-task=3" will get you 4 hyperthreads (2 CPU cores).

So, whenever you see a "cpu" limit below, remember that's actually a "hyperthread", and you can't actually request 1 "cpu", you will always get an even number.

On to the good stuff.

## How to see your group limits

The full (but slightly unreadable) resource limit configuration can be seen with the command scontrol show assoc_mgr. The full (and equally unreadable) resource requests for queued and running jobs can be seen with the command scontrol show jobid NNNN. Relating the information from both commands can be quite a bit of work. Fortunately, some kind soul (<https://github.com/OleHolmNielsen/Slurm_tools>) has witten some tools that make this a whole lot easier. The most useful of these are available on the submit hosts, in /usr/local/bin.

To see your group limits, use the command showuserlimits. Without arguments, it shows the limits for your default "account". You can also specify -A someotheraccount or -u someotheruser.

Let's see the output of showuserlimits -u mmarinus -A bofh (my limits are very low, because I don't actually pay to use the cluster; I get payed so that you can use it...)

I'll add some comments inline.

**mvanburen@hpcs05 \$ showuserlimits -u mvanburen -A bofh**



Association (Parent account): 
ClusterName = udac   # this is the same for everyone 
Account = bofh   # this is my "account" (the group that has all the actual limits) 
UserName =   # no username, this applies to every membr of my account group 
Partition =   # no partition, this applies to all partitions 
Priority = 0 
ID = 3 
SharesRaw/Norm/Level/Factor = 8/0.00/18909/0.00   # Let's discuss this another time :-) 
UsageRaw/Norm/Efctv = 1.99/0.00/0.00 
ParentAccount = root, current value = 1 
Lft = 1694 
DefAssoc = No 
GrpJobs =   # This line (and the next 4) are limits that could have been set, but are not 
GrpJobsAccrue = 
GrpSubmitJobs = 
GrpWall = 
GrpTRES = 
cpu: Limit = 1882, current value = 0   # this is the first actual limit: I can use no more than 1882 CPU's simultaneously (one job using 1882, or 188 jobs using 10, etc). If I submit more, they stay "pending". 
mem: Limit = 7000000, current value = 0   # My running jobs can not request more than 7 TB memory. If I request additional memory, that jobs stay pending. 
gres/gpu: Limit = 8, current value = 0   # I can not use more than 8 GPU's simultaneously

GrpTRESMins =   # this would set limits on total resource consumption, including past jobs. We don't do this, we only limit current resource usage.

GrpTRESRunMins =   # this limits "requested_runtime \* specified_resource" for running jobs. Time is in minutes. 
cpu: Limit = 17818, current value = 0   # I can have 1 jobs with 2 CPU's requesting 8909 minutes, or 10 jobs with 10 CPU's requesting 178.18 minutes, etc. Additional jobs stay pending. 
gres/gpu: Limit = 20160, current value = 0   # I can have 1 job with 1 GPU requesting 20160 minutes, or 4 jobs with 2 GPU's requesting 2520 minutes, etc.

MaxJobs =   # That is all we limit on. 
MaxJobsAccrue = 
MaxSubmitJobs = 
MaxWallPJ = 
MaxTRESPJ = 
MaxTRESPN = 
MaxTRESMinsPJ = 
MinPrioThresh = 
Association (User):   # This would show any limits that are applied to me individually, rather than to my group. Nothing here, we only limit groups. 
ClusterName = udac 
Account = bofh 
UserName = mmarinus, UID=10307 
Partition = 
Priority = 0 
ID = 4 
SharesRaw/Norm/Level/Factor = 10/0.00/50/0.00 
UsageRaw/Norm/Efctv = 1.99/0.00/1.00 
ParentAccount = 
Lft = 1705 
DefAssoc = Yes 
GrpJobs = 
GrpJobsAccrue = 
GrpSubmitJobs = 
GrpWall = 
GrpTRES = 
GrpTRESMins = 
GrpTRESRunMins = 
MaxJobs = 
MaxJobsAccrue = 
MaxSubmitJobs = 
MaxWallPJ = 
MaxTRESPJ = 
MaxTRESPN = 
MaxTRESMinsPJ = 
MinPrioThresh =



## FAQ about SLURM

**Extra information** : 
[https://slurm.schedmd.com/](https://slurm.schedmd.com/) 
[https://slurm.schedmd.com/tutorials.html](https://slurm.schedmd.com/tutorials.html) 
<https://github.com/aws/aws-parallelcluster/wiki/Transition-from-SGE-to-SLURM> 
<http://hpcstats.op.umcutrecht.nl/> 
[https://slurm.schedmd.com/pdfs/summary.pdf](https://slurm.schedmd.com/pdfs/summary.pdf)


---

# Software & Environments

## Software Overview

> **Summary:** Software installation patterns: user-space installs in /hpc/local/Rocky8/<group>/, conda environments, R package installation (install.packages with lib path), Python venv setup, compiling from source. Covers permission model and group directories.

You can installl you own software in  a group specific **directory** hat is made available for this purpose:



/hpc/local/osversion/group/



Note that **OS-version** is the current Linux version and group is your own group name. Here, you can install any software you like and maintain it yourself.

## Software of general interest

If you find a software to be of general interest to HPC users, let know. We can provide it as an software module or install it as a system package (rpm) 
and update it on a regular basis.

However, if you are dependent on a specific version of a software package and don't want regular updates, we advise you to install it yourself and encourage you to take the benefits of Making software available using LMOD

## How to install your own software

A specific directory is made available for group-specific software to be installed:



/hpc/local/osversion/group/



## Compile C software

You can download your C software of interest and unpack it in this directory. 
Typically, a pre-installation configuration is done by executing:



./configure --prefix=/hpc/local/osversion/group/package



This will create a "Makefile" which explains to the "make" utility how the software should be compiled, and where the software will be installed. The 'prefix' is the top directory under which the whole package will be installed. You may want to include the package version number in the name of this directory; that way you can install more than one version next to each other. Use symlinks to point to the 'default' installation.

After the configure step, you compile the software using:



make



The Makefile will be read, building the application binaries. To install these binaries, use:



make install



That is it! You can check the user documentation of the installed software for details of how to run the application.

## Python modules

Create your virtual software environment for a specific Python project with Python Virtual Environment: 
see :  <https://docs.python.org/3/library/venv.html>



\#activate the virtual environment 
source /path/to/new/virtual/environment/bin/activate 
\#use pip to install python modules in the virtual environment 
pip list 
pip install \<module\>



## Your own R version

Go to [https://cran.r-project.org/mirrors.html](https://cran.r-project.org/mirrors.html), download the latest "R-3.0.whatever.tar.gz" file to a submit host (hpcs05/hpcs06). Copy this file to a directory that has enough space (about 300M). In this case, let's assume /tmp, but your homedir probably has enough space as well.



cd /tmp 
wget [http://cran-mirror.cs.uu.nl/src/base/R-3/R-3.0.2.tar.gz](http://cran-mirror.cs.uu.nl/src/base/R-3/R-3.0.2.tar.gz) 
tar -zxvf R-3.0.2.tar.gz 
cd R-3.0.2



Now, we'll have to "**configure**" and "**make**" this:



./configure --prefix=/hpc/local/Rocky8/bofh/R-3.0.2 
make 
make install



Where you replace "/hpc/local/Rocky8/bofh/R-3.0.2" with some path where you have write-access. 
Something like "/hpc/local/Rocky8/YOURGROUP/R-3.0.2" would probably be a good choice.

Now, you would start this version of R by entering the full path:



/hpc/local/Rocky8/bofh/R-3.0.2/bin/R



Or by adding the directory /hpc/local/Rocky8/YOURGROUP/R-3.0.2/bin to your own PATH (e.g. in your \$HOME/.bash_profile).

## R packages

Packages can easily be installed inside R by providing a local path:



R 
install.packages( "yourLibrary", lib = "/hpc/local/osversion/group/path" ) 
library( "yourLibrary", lib.loc = "/hpc/local/osversion/group/path"



Alternatively, you can customize your Linux environment variables and set **R_LIBS** to /hpc/local/osversion/group/path. 
This way, you can leave out the path specification in R.

**Check**



module load R 
R 
find.package('\<mypackage\>')



## Perl libraries

To install **CPAN** perl libraries, you first have to instruct CPAN which directory to use. You can do this by modifying your CPAN configuration, from within the CPAN shell:



cpan 
o conf mbuildpl_arg "installdirs=site install_base=/hpc/local/osversion/group" 
o conf makepl_arg "INSTALLDIRS=site INSTALL_BASE=/hpc/local/osversion/group" 
o conf prefer_installer MB 
o conf prerequisites_policy follow 
o conf commit



After this, CPAN should install all perl libraries in the appropriate directory such that they are available on the entire cluster. 
Your **PERLLIB** environment variable should be set to include /hpc/local/OSVERSION/GROUP/lib/perl5.

In the past, the environment variable **PERL_INSTALL_ROOT** used to be used for cpan installs, but that doesn't work anymore and wreaks havoc on the install if you use the cpan configuration shown above. I.o.w., be sure not to define PERL_INSTALL_ROOT.

If you later just wish to install packages, you can use the **cpan -i **command from the command line. No need to startup the CPAN shell.

### Making software available using [Lmod](#lmod-modules)

### Making software available using APPTAINER (formerly SINGULARITY)

[Apptainer ](https://apptainer.org/docs/user/latest/)  (docker compatible but more secure) is available on the compute-nodes (n0XXX). 
You can download Docker or Apptainer images for applications and run your programs in **apptainer**. 
For example running [R and SAIGE module](https://saigegit.github.io/SAIGE-doc/): 
You can execute this in a login session.

**SAIGE on Apptainer(image)**

Download an image for SAIGE on a compute node:



apptainer pull [docker://wzhou88/saige:1.5.0](https://hub.docker.com/r/wzhou88/saige)



Login into the container



apptainer shell -B /tmp:\$TMPDIR ./saige_1.5.0.sif



Check if SAIGE is available



pixi shell --manifest-path /app

R 
\>installed.packages() 
\>q() 
\>n

exit



To run a R script in the container create 1.R with following content:



library("SAIGE") 
print("Hello World!") 



\# You can run this in a sbatch script 
\# Run your code by :



apptainer exec -B /tmp:\$TMPDIR ./saige_1.5.0.sif pixi run --manifest-path /app Rscript 1.R

## Conda

> **Summary:** Miniforge setup: wget Miniforge3-Linux-x86_64.sh, conda-forge channel default, bioconda channel addition. Environment management: conda create -n envname, conda activate. Migration from defaults channel to conda-forge.

Conda is an open-source **package manager** and environment management system. While the base conda tool itself is free, some distributions (Anaconda/Miniconda) include features such as the *defaults* channel that require a paid license for organizations like UMC Utrecht.

To avoid licensing issues, please use the **Miniforge** distribution, which only enables free features.

**Important:**

- Do **not** install Miniforge in your home folder. Conda environments can grow large and easily exceed the home storage limits.
- Instead, create a personal installation folder under your group storage directory (/hpc/...), and run the installer interactively as follows:





cd /hpc/path/to/your/folder 
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh 
bash Miniforge3-Linux-x86_64.sh -bcp \$(pwd)/miniforge3

The base conda environment will be active after next login or by starting a new shell session. By default, Miniforge activates only the **conda-forge** channel. If needed, you can also add additional public channels such as **Bioconda** (<https://bioconda.github.io/>).





conda config --add channels bioconda 
conda config --add channels conda-forge 
conda config --set channel_priority strict

To install Jupyter Notebook in the base environment for use on the Open OnDemand web portal, run:





conda install jupyter

## Conda environments in Jupyter Notebooks

If you want to switch between different conda environments in Jupyter Notebooks on the Open OnDemand web portal, please read: 
[Conda Environments in Jupyter Notebooks](https://towardsdatascience.com/get-your-conda-environment-to-show-in-jupyter-notebooks-the-easy-way-17010b76e874)

## Transition from Anaconda/Miniconda

If you are currently using Anaconda or Miniconda, we recommend transitioning to Miniforge. Instructions for this migration can be found here: 
<https://conda-forge.org/docs/user/transitioning_from_defaults/>

## Lmod Modules

> **Summary:** Environment modules: module avail, module load <name>, module list, module purge. Custom modulefiles in /hpc/local/Rocky8/<group>/modules/. Covers writing modulefiles with prepend_path and setenv.

## Introduction

Often a program requires particular environment variables in order to run. LMOD environment modules provide a convenient way to meet these requirements in a dynamical way. By creating modulefiles for your softwares it will be easy to add and remove directories to the PATH,LIBRARY_PATH,MANPATH,CLASSPATH and many other environment variables just by loading and unloading the module(file). This will allow for easily changing the environment (variables) and or software versions. Here an introduction on how to create these software module files.

## Case

Lets assume we want program PROGRAM with version VERSION to become available as a software module.

- PROGRAM (e.g. samtools, plink, bedtools)
- VERSION (e.g. 1.3, 2, 2.4.8)

For creating your own modules replace PROGRAM and VERSION according to the program of version that you are about to install

## Get and install the program in a standardized way



\$wget [https://url/to/PROGRAM-VERSION.tar.gz/download](https://url/to/PROGRAM-VERSION.tar.gz/download) 
\$tar -zxvf PROGRAM-VERSION.tar.gz 
\$cd PROGRAM-VERSION 
\$configure --prefix=\$HOME/\$MY_DISTRO/software/PROGRAM-VERSION 
\$make -j4 
\$make install



## Make your own (cluster distribution specific) software modules visible when you login

This needs to be added once to your \$HOME/.bash_profile After changing your .bash_profile also update your environment by invoking \`source ~/.bash_profile\`

**MY PRIVATE SOFTWARE MODULES**



privatemodules=\$HOME/\$MY_DISTRO/etc/modulefiles 
if \[ -d \\privatemodules \];then 
   MODULEPATH=\$privatemodules:\$MODULEPATH 
fi



## 

## Create a module file for the program

These module files should end up in a path that is defined in the \$MODULEPATH environment variable It might be convenient to to name the module after the program name



\$mkdir -p \$HOME/\$MY_DISTRO/etc/modulefiles/PROGRAM



The lines cat..EOF should be copied in a (script) file and modified according to your (PROGRAMs) needs At least replace PROGRAM and VERSION and execute the file (script)



cat \<\<EOF\>\>\$HOME/\$MY_DISTRO/etc/modulefiles/PROGRAM/VERSION.lua 
help( 
\[\[PROGRAM(version VERSION) Just Another Algorithm. It is a program for analysis of again something using a simulation and not wholly unlike another program. 
JAA is licensed under the ShareYourCode License. You may freely modify and redistribute it under certain conditions 
(see the file COPYING for details). - Homepage: [http://JAA.sources.notyet](http://JAA.sources.notyet) \]\]





whatis("JAA (version VERSION) Just Another Algorithm. It is a program for analysis of again something using a simulation not wholly unlike another program. - Homepage: [http://JAA.sources.notyet](http://JAA.sources.notyet)")





local version = "VERSION" 
local base = "/hpc/local/\\MY_DISTRO/\\MY_GROUP/software/PROGRAM-" .. version





conflict("PROGRAM")





prepend_path("LD_LIBRARY_PATH", pathJoin(base, "lib")) 
prepend_path("LIBRARY_PATH", pathJoin(base, "lib")) 
prepend_path("PKG_CONFIG_PATH", pathJoin(base, "lib/pkgconfig")) 
prepend_path("MANPATH", pathJoin(base, "share/man")) 
prepend_path("PATH", pathJoin(base, "bin")) 
EOF



## remarks

- In lua lines starting with -- are interpreted as comments
- The number of environment variables that need to be set (prepend_path lines) to make your program running depends on the needs of your program.
- If the program of requires another software module (e.g. a particular Java) to be loaded, this can be automated by adding lines like lines like:



load("Java/1.8.0_60") 
prereq("Java/1.8.0_60")



## Check module file

Once you have installed the program and created its module file lets see if the module is available:



\$module spider



If it does not appear check if the module (lua) file is in the right path.



\$module load PROGRAM



Should load dependencies (if exists) and report on any changes in the environment In case of (lua) syntax errors it will show the line number that has an error.

Now check if the environment variables have been changed according to the module file and the programs needs e.g.



\$echo \$PATH 
\$echo \$MANPATH 
\$echo \$CLASSPATH



Also check if unloading the module restores the environment



\$module unload PROGRAM



## Share

Once you are convinced that the module file is working correctly please let your group members also benefit from it. Sharing is easy!

- Move the install directory:



\$mv \$HOME/\$MY_DISTRO/software/PROGRAM-VERSION  /hpc/local/\$MY_DISTRO/\$MY_GROUP/software/PROGRAM-VERSION



- Make adjustment in the "local base" line in the module file [(see remarks)](https://wiki.bioinformatics.umcutrecht.nl/bin/view/HPC/MakingSoftwareAvailableUsingLMOD#RemarksModuleFile) and move the module file:



\$mv \$HOME/\$MY_DISTRO/etc/modulefiles/PROGRAM  /hpc/local/\$MY_DISTRO/\$MY_GROUP/etc/modulefiles/PROGRAM



Allow your group members to add (module files) of other version of the program by making the PROGRAM directory writable:



\$chmod 770 /hpc/local/\$MY_DISTRO/\$MY_GROUP/etc/modulefiles/PROGRAM

## Migrating to conda-forge

> **Summary:** Channel migration procedure: backup existing env, conda config --add channels conda-forge, conda config --set channel_priority strict. Troubleshooting dependency conflicts.

DISCLAIMER: Conda environments can be complex and therefore we cannot guarantee that the instruction on this page will work in all cases. Please try the different options suggested and in case of problems feel free to ask us via HPCSupport@umcutrecht.nl

Here we provide some ways to convert or recreate an existing conda environment and fully migrate packages from the Anaconda 'defaults channel ' to the conda-forge / bioconda channels. 

### Backup

Before migrating it is advisable to make backup of the existing environment or conda installation folder:





cp -a /path/to/condafolder /path/to/condafolder.backup

### Clone/export

Export an list of all packages of the environment and create a clone with:





conda env export --from-history --prefix /path/to/environmentname \> environmentname.yml 
conda config --remove channels defaults 
conda create -n environmentname-clone --clone environmentname --offline

### Reinstall from conda-forge

This can be done by either updating all in the existing environment explicitly from the conda-forge channel. This sometimes fails due to dependencies that are not resolved correctly, in that case it also possible to recreate the environment by based on the exported package list. 





conda env export -n \<yourenvironmentname\> --from-history --ignore-channels --format txt -f \<yourenvironmentname\>.txt 
conda create -n \<yourenvironmentname-forge\> -c conda-forge --override-channels --no-default-packages --file \<yourenvironmentname\>.txt 
conda env remove -n \<yourenvironmentname\> 
conda rename -n \<yourenvironmentname-forge\> \<yourenvironmentname\> 

Please note, that in case you use python in the environment and installed package with pip you will need to reinstall these also again.


---

# Cluster Setup & Resources

## Setup Overview

> **Summary:** Cluster architecture overview: submit hosts (hpcs05/hpcs06), compute nodes, storage hierarchy (/home, /hpc/shared, /scratch). Account model, group directories, quota information.

## Data Security / data separation

The HPC is a shared environment in the sense that multiple groups run their software on a shared set of compute nodes. This does not mean that all data is shared. Data security and data separation does require some thought and planning from the [participating groups](#participation-groups) to adjust the level of protection on the data as needed, for example to meet the segregation of duties requirements.

## POSIX filesystem Security

File security is based on the standard Unix filesystem security, in which the "owner", the "group" and "others" can have certain permissions (read/write/execute). By default, these permissions will be set to a secure state (see below).

Note that the HPC administrators have the ability to read/write/execute your files, but will not without your permission for each situation where this access is needed.

## Filesystem locations

There are several locations to store your files.

- Your homedirectory, which by default is only accessible by you. Other users cannot read this directory, unless you set more permissive permissions yourself. It should contain things like login-scripts, personal configuration files, etc. By default, this is a secure, but small, location.



- Several group directories (/hpc/local, /hpc/shared, /hpc/groupname). By default, these locations are readable by the other members of your group, but are not accessible by people in other groups. Typically it contains files and directories containing your research data.



- Several locations that are shared by all users of the HPC: /tmp, /hpc/tmp. By default, data you store here (temporarily!) will be readable by other users of the system; do not expect any form of data security here.

## Group based access

Most of the above locations provide access based on a "group" level.

Best practice dictates that your data should be accessible by as few people as possible. If you process humane data, then this is a GDPR/AVG **requirement**.

If the default group that you are in (the "project" in which your computations are done) does not sufficiently restrict the access to a particular set of data, a **new group** can be created for this purpose. Just e-mail us (<hpcsupport@umcutrecht.nl>) to have a new group created for this project/data (including the users that should have access). Next, put the data in a separate directory, set the group-ownership to this new group, remove the access rights for "others" and all data access will be restricted to this group.

If needed, we strongly encourage you to create a new folder and new group for each study to enable segregation.

## General architecture

The HPC infrastructure consists of a large set of interconnected servers. 
Users access the HPC infrastructure via one of the two login/submission servers hpcs05 and hpcs06. Here, computing jobs can be submitted. 
These jobs are then automatically queued by the queue master server hpcm007 and distributed to the compute nodes n0062 to n0136. 
Each compute node consists of 12 .. 48 cores. HPC compute nodes and storage servers are connected for fast and concurrent data access.

## [SLURM](#slurm-guide) software

is used to manage the User-accounts , jobs,  logs and accounting.

## Directories

Directories of the HPC storage servers are mounted to the login/submission servers hpcs05 and hpcs06.

A home directory : 
**/home/group/user/**

is provided for each user, with 7 GB available disk space per user. Files in this folder are only accessible to the user. This space should only be used for small, personal files; not for files (log files, input files, output files) that you will use from the compute nodes!

In addition, two group-specific directories are provided for each group. The first group-specific directory : 
**/hpc/local/version/group/** 

can be used to install group-specific libraries and software. Do **not** read or write datafiles here. The second group-specific directory

**/hpc/shared/group/**

provides shared disk space for data storage only for TRIAL users . Permissions may be changed to allow other groups access to your data. 
At this moment, the group-specific folders ( local and shared) are granted 1 TB and 10 TB disk space in total, that is for all research groups together. 
Additional group-specific disk space may be rented in

**/hpc/group**

on a per Terabyte, per year basis ( [ContactDetails](#contact)). 
**/hpc/shared/group** and **/hpc/group** are both stored on performant storage. 
These are the places to read/write data from the compute nodes.

On every compute node is 8 GB available in : **/tmp**

but be aware that this space is shared between every user, so if you want to use this area:

- Anticipate on the fact that /tmp might be full.
- For each job, a scratch directory with 1 GB is automatically created when the job starts running, and is automatically cleaned up afterwards. The name of this directory is stored in the environment variable **"\$TMPDIR"** . The easiest way to ensure that your files are cleaned up properly, is to use this environment variable. The default size is 1 GB and more space can be requested with slurm as explained [here](#slurm-guide).

## Fair share usage

Jobs are scheduled according to a fair share usage scheme. Each group participating in the HPC project is given a number of share tickets dependent on the financial investments made. Scheduling of jobs depend on the shares of a group and the accumulated past usage of that group. Usage is adjusted by a decay factor, a half-life of one week, such that "old" usage has less impact. The potential resource share of a group is constantly adjusted. Jobs associated to groups that consumed fewer resources in the past are preferred in the scheduling. At the same time, full resource usage is guaranteed, because unused shares are available for pending jobs associated with other groups. In other words, if a group does not submit jobs during a given period, the resources are shared among those who do submit jobs.

## Hardware overview

All servers are Dell PowerEdge systems .

- 57 compute-CPU-nodes
- 18 compute-GPU-nodes
- 2 gateway servers
- 2 submit servers
- 3 transfer servers
- 1 cromwell server
- 2  Slurm management servers
- 16 EMC isilon nodes for HPC-storage
- 6 EMC islon nodes for HPC-archive storage
- Cisico ACI network leafes and spines achitecture

## Resource Monitoring

Hardware and runing software is monitored by a icinga installation.

## Conditions

In order to be able to use the HPC facility, you need to be affiliated with University Medical Center Utrecht, Utrecht University, Hubrecht Institute or Princess Maxima Center for pediatric oncology. This means that you either need to be employed by one of these institutes or you need to have a "gastvrijheidsverklaring". The responsibility to ensure that this is the case is up to the principal investigator of the individual research groups locate in one of these institutes.

By using the HPC facility you also comply with the following policies:

- You are familiar with the guidelines of scientific conduct set forth by UMC Utrecht, Utrecht University, Hubrecht Institute or Princess Maxima Center.
- If applicable, you are familiar with and comply with the latest legislation concerning patient-related research.
- Patient-related research data are not allowed on the HPC infrastructure. However, if the data has been (pseudeo)anonymized beforehand, so that samples cannot be traced back to individual subjects, you can use this data on the HPC infrastructure.
- Abuse of HPC infrastructure resources may result in termination of the user account.

## Support

Support for the HPC facility is provided on a "best effort" basis. This means that we will do our utmost best to keep the infrastructure running at all times, but that we cannot and will not guarantee 100% up time and do not have 24/7 support. Support requests are taken care of during normal working hours (weekdays, 9.00-17.00) and you can expect us to reply within a day. During weekends and evenings, we do typically monitor support requests and respond if possible, but this depends heavily on the availability and willingness of our support team to do this during their free time. No guarantees about response times will be given and/or can be claimed about support requests made during the weekend or evening. If not handled during this period, they will be taken care of the next working day.

Support requests should be directed to <hpcsupport@umcutrecht.nl>, only then can we guarantee that we are able to provide the support as indicated here.

To avoid confusion, we also want to be clear on what we support:

- Hardware support for compute nodes if a valid hardware support contract with the hardware supplier is in place.
- General Operating System maintenance (security updates, software fixes, monitoring and management).
- Configuration, optimization, maintenance and monitoring of the queueing engine and available resources.
- Configuration, optimization, maintenance and monitoring of the HPC storage system.
- Configuration, optimization, maintenance and monitoring of the HPC submit hosts and master hosts.

In addition, we try to assist/advise on the following topics, but cannot guarantee that we are able to provide a solution:

- Compilation, installation and configuration of group-specific software packages.
- Resolve simultaneous peak performance needs of different groups.
- Implementation, configuration and optimization of bioinformatics workflows/pipelines.

## Your Privacy

The European General Data Protection Regulation (GDPR) (Dutch: Algemene Verordening Gegevensbescherming) requires us to disclose the information that we gather about you, what we use it for, and for how long we store this information. Please note that under the GDPR, you have certain additional rights (the right to see the information we have about you, the right to be forgotten, etcetera). We invite you to read the GDPR, and if you want to exercise any of these rights, please let us know (<hpcsupport@umcutrecht.nl>) and we'll help you to the best of our abilities.

The HPC facility falls under the jurisdiction of the UMC Utrecht, so all the terms and regulations that are listed in the UMC Utrecht privacy statement (URL not known yet, will be added later) apply to us as well. Below, we will outline what we specifically, as HPC, gather and store about you.

## Some personal information

The HPC user database contains your name, your e-mail address, and in some cases your telephone number. We need your e-mail address to be able to inform you about current affairs (e.g., planned downtime). We use the telephone number to be able to contact you for urgent incidents (e.g., anomalous use of the system, suspected account abuse). We keep this data for as long as your account is active, and a maximum of 6 months after that. After this period, your personal data will be removed from the account. The account itself is kept, in a disabled state, because not all your files are removed (see below), and they need an owner.

### Your files

The HPC is not a place to store "personal" files. We expect your files to contain work-related material only. This can never be identifyable human/patient data! You must (pseudo) anonimyze the data and keep the key (if applicable) in the 'closed/care' network. It is the PI's responsibility that this is strictly enforced.

File security is based on the standard Unix filesystem security, in which the "owner", the "group" and "others" can have certain permissions (read/write/execute). By default, these permissions will be set to a secure state (see below). Note that the HPC administrators have the ability to read/write/execute your files, but will not do so without your permission.

There are several places to store your HPC files.

- Your homedirectory, which by default is only readable by you. Other users cannot read this directory, unless you set more permissive permissions yourself. This directory will be removed 6 months after your HPC account is deactivated. It should contain things like login-scripts, personal configuration files, etc.



- Several group directories (/hpc/local, /hpc/shared, /hpc/groupname). By default, these locations are readable by the other members of your group, but are not accessible by people in other groups. Files and directories you create here should contain the majority of your research data. These files and directories will not be removed after your account has been disabled, as they may be relevant for other group members.

Please remember that the HPC storage is NOT backupped. It is a professional storage system well protected against hardware failures, but if you delete/overwrite a file it is permanent!

## Login data

When you log in to our systems, we store the time that you log in and out, and the IP address you came from. We keep this information for 6 months.

We need this information to monitor account usage, and to be able to detect anomalous logins: "This person is suddenly logging in from several places around the globe; perhaps the account is hacked".

## Job data

For every HPC job you submit, some data is stored in our database. Most information is purely technical (which node did it run on, what is the job number, how much CPU and memory did it use), and some information could be construed to be personally identifiable.

These are: your username, the group you submitted the job for, the submission time, and the job name.

The data gathered about user jobs is basically the core register of the HPC system. We need it to monitor, diagnose, and predict how our groups are using our system, for billing and capacity planning. Therefore, we keep this data for no less than 7 years.



Price list



1 CPU share (€ 1200) : ~50.000 CPU hrs 
1 GPU share (€ 1200): ~5.000 GPU hrs (includes 6 CPUs) 
1 TB non-redundant high-performance storage (€ 180/TB/year) 
1 TB non-redundant low-performance/archive storage (€70/TB/year)

## The Compute-Nodes in the Cluster

All the specs of all the compute nodes can be found  [here](#cluster-architecture)

## Cluster Architecture

> **Summary:** High-level cluster topology: login nodes, compute partitions, network fabric. Entry point to detailed node specifications.

**All Compute Nodes in the HPC cluster**



- [All Compute-nodes](#all-compute-nodes)
- [All CPU-nodes](#cpu-nodes)
- [All GPU-nodes](#gpu-nodes)

## CPU Nodes

> **Summary:** CPU partition specs: node count, CPU models, cores per node, RAM per node, hyperthreading (SLURM 'cpu' = hyperthread). Useful for capacity planning sbatch requests.

| Name | Mem | CPU# | CoresPerCpu# | TotalCores | CPUspeed | TMPspaceGb |
|-------|------|------|--------------|------------|----------|------------|
| n0061 | 256 | 2 | 12 | 24 | 2500 | 1000 |
| n0062 | 384 | 2 | 18 | 36 | 2133 | 2000 |
| n0063 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0064 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0065 | 1023 | 4 | 12 | 48 | 2300 | 2000 |
| n0067 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0068 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0069 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0070 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0071 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0072 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0073 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0074 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0075 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0076 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0077 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0078 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0079 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0080 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0081 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0082 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0083 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0084 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0085 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0086 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0087 | 384 | 2 | 20 | 40 | 2600 | 2000 |
| n0088 | 384 | 2 | 20 | 40 | 2600 | 2000 |
| n0089 | 384 | 2 | 20 | 40 | 2600 | 2000 |
| n0090 | 384 | 2 | 20 | 40 | 2600 | 2000 |
| n0091 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0092 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0093 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0094 | 386 | 2 | 20 | 40 | 2400 | 2000 |
| n0095 | 384 | 2 | 20 | 40 | 2400 | 2000 |
| n0103 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0104 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0105 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0106 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0107 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0109 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0110 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0111 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0112 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0113 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0114 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0115 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0116 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0117 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0118 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0119 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0120 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0121 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0122 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0123 | 384 | 2 | 20 | 40 | 3100 | 1300 |
| n0134 | 1024 | 2 | 16 | 32 | 2800 | 1500 |
| n0135 | 1024 | 2 | 16 | 32 | 2800 | 1500 |
| n0136 | 1024 | 2 | 16 | 32 | 2800 | 1500 |

## GPU Nodes

> **Summary:** GPU partition specs: GPU models (Tesla P100/V100, RTX 6000, A100), GPUs per node, VRAM, associated CPU/RAM. Request syntax: -p gpu --gpus-per-node=<type>:<count>.

| Name | Mem | CPU# | CoresPerCpu# | TotalCores | CPUspeed | TMPspaceGb |
|-------|-----|------|--------------|------------|----------|------------|
| n0096 | 256 | 2 | 12 | 24 | 2700 | 2000 |
| n0097 | 256 | 2 | 12 | 24 | 2200 | 625 |
| n0098 | 384 | 2 | 12 | 24 | 2700 | 2000 |
| n0099 | 384 | 2 | 12 | 24 | 2700 | 2000 |
| n0100 | 384 | 2 | 12 | 24 | 2700 | 2000 |
| n0101 | 384 | 2 | 12 | 24 | 2700 | 2000 |
| n0102 | 384 | 2 | 12 | 24 | 2700 | 2000 |
| n0108 | 384 | 2 | 16 | 32 | 2900 | 1300 |
| n0124 | 512 | 2 | 24 | 48 | 2800 | 1400 |
| n0125 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0126 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0127 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0128 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0129 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0130 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0131 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0132 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0133 | 512 | 2 | 24 | 48 | 2800 | 1700 |



**Available GPU cards**



| Node  | GPUcard  |  Slurm-device |
|----|----|----|
| n0096 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0097 | GPU 0: Tesla P100-PCIE-16GB  |  tesla_p100-pcie-16gb |
|   | GPU 1: Tesla P100-PCIE-16GB  |  tesla_p100-pcie-16gb |
| n0098 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0099 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0100 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0101 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0102 | GPU 0: Quadro RTX 6000  |  quadro_rtx_6000  |
|   | GPU 1: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 2: Quadro RTX 6000  |  quadro_rtx_6000 |
|   | GPU 3: Quadro RTX 6000  |  quadro_rtx_6000 |
| n0108 | GPU 0: Tesla V100-PCIE-16GB |  tesla_v100-pcie-16gb (1x)  |
|   | GPU 1: Tesla V100-PCIE-16GB  |  tesla_v100-pcie-16gb (1x) |
|   | GPU 2: Tesla V100-PCIE-16GB  |  tesla_v100-pcie-16gb (1x)  |
|   | GPU 3: Tesla V100-PCIE-16GB  |  tesla_v100-pcie-16gb (1x)  |
| n0124 | GPU 0: NVIDIA A100 80GB PCIE (divided in 3) |  2g.20gb  (3x) |
|   | GPU 1: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
| n0125 | GPU 0: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
|   | GPU 1: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
| n0126 | GPU 0: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
|   | GPU 1: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
| n0127 | GPU 0: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
|   | GPU 1: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
| n0128 | GPU 0: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
|   | GPU 1: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
| n0129 | GPU 0: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
|   | GPU 1: NVIDIA A100 80GB PCIE |  7g.79gb  (1x) |
| n0130 | GPU 0: NVIDIA A100 80GB PCIE  |  7g.79gb  (1x) |
|   | GPU 1: NVIDIA A100 80GB PCIE  |  7g.79gb  (1x) |
| n0131 | GPU 0: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
|   | GPU 1: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
| n0132 | GPU 0: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
|   | GPU 1: NVIDIA A100 80GB PCIE (divided in 3)  |  2g.20gb  (3x) |
| n0133 | GPU 0: NVIDIA A100 80GB PCIE  |  7g.79gb (1x) |
|   | GPU 1: NVIDIA A100 80GB PCIE  |  7g.79gb (1x) |

\# scontrol show nodes

## All Compute Nodes

> **Summary:** Complete node inventory table: hostname, partition, CPUs, RAM, GPUs, local scratch. Reference for --nodelist targeting or understanding squeue output.

| Name | Mem | CPU# | CoresPerCpu# | TotalCores | CPUspeed | TMPspaceGb |
|-------|------|------|--------------|------------|----------|------------|
| n0061 | 256 | 2 | 12 | 24 | 2500 | 1000 |
| n0062 | 384 | 2 | 18 | 36 | 2133 | 2000 |
| n0063 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0064 | 384 | 2 | 18 | 36 | 2300 | 2000 |
| n0065 | 1023 | 4 | 12 | 48 | 2300 | 2000 |
| n0067 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0068 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0069 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0070 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0071 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0072 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0073 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0074 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0075 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0076 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0077 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0078 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0079 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0080 | 384 | 2 | 18 | 36 | 2300 | 1000 |
| n0081 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0082 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0083 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0084 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0085 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0086 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0087 | 384 | 2 | 20 | 40 | 2600 | 1000 |
| n0088 | 384 | 2 | 20 | 40 | 2600 | 1000 |
| n0089 | 384 | 2 | 20 | 40 | 2600 | 1000 |
| n0090 | 384 | 2 | 20 | 40 | 2600 | 1000 |
| n0091 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0092 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0093 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0094 | 386 | 2 | 20 | 40 | 2400 | 1000 |
| n0095 | 384 | 2 | 20 | 40 | 2400 | 1000 |
| n0096 | 256 | 2 | 12 | 24 | 2700 | 1000 |
| n0097 | 256 | 2 | 12 | 24 | 2200 | 1000 |
| n0098 | 384 | 2 | 12 | 24 | 2700 | 1000 |
| n0099 | 384 | 2 | 12 | 24 | 2700 | 1000 |
| n0100 | 384 | 2 | 12 | 24 | 2700 | 1000 |
| n0101 | 384 | 2 | 12 | 24 | 2700 | 1000 |
| n0102 | 384 | 2 | 12 | 24 | 2700 | 1000 |
| n0103 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0104 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0105 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0106 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0107 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0108 | 384 | 2 | 16 | 32 | 2900 | 1000 |
| n0109 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0110 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0111 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0112 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0113 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0114 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0115 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0116 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0117 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0118 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0119 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0120 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0121 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0122 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0123 | 384 | 2 | 20 | 40 | 3100 | 1000 |
| n0124 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0125 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0126 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0127 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0128 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0129 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0130 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0131 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0132 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0133 | 512 | 2 | 24 | 48 | 2800 | 1700 |
| n0134 | 1024 | 2 | 16 | 32 | 2800 | 1500 |
| n0135 | 1024 | 2 | 16 | 32 | 2800 | 1500 |
| n0136 | 1024 | 2 | 16 | 32 | 2800 | 1500 |

## HPC User Council

> **Summary:** Governance: user council meeting schedule, feedback channels, policy discussions. Contact for cluster-wide issues or feature requests.

To steer future directions for the high-performance computing (HPC) research infrastructure, a HPC user council has been setup. 
This council will advise and decide on how to proceed, given the financial budget and project plan set forth by the research ICT steering committee and the functional requirements HPC. 
Within the HPC user council, two types of members exist, contributing members and advisory members.

Contributing members are members that have invested financial resources into the HPC research infrastructure and therefore have a vote in deciding on proposals put forward by the working team HPC. 
Each individual research group that has invested either in HPC compute nodes or HPC storage is represented by one contributing member. 
Advisory members have a more advisory role and can suggest future directions, give technical input and assist the working team HPC if required, but do not have a vote when deciding on proposals.

The working team HPC will prepare proposals for the implementation, continuation and development of the HPC research infrastructure, based on the wishes put forward by the contributing members and taking into account the input from the advisory members. 
The working team HPC also has a vote in deciding on proposals. 
Proposals will be discussed and decided on during HPC user council meetings, which will take place approximately every two months.

When deciding on proposals, a consensus decision amongst the contributing members and the working team HPC must be reached. 
Amendments to the functional requirements HPC can be proposed by contributing members to the working team HPC, after which they will be discussed in the next user council meeting and if a consensus is reached, the functional requirements HPC will be changed accordingly. 
A consensus is reached if two-thirds of the contributing members and the working team HPC agree.

If a consensus decision between the contributing members of the HPC user council and working team HPC cannot be reached, the proposal will be forwarded to the research ICT steering committee, who will then decide on how to proceed.

## Participation Groups

> **Summary:** Account/group model: how compute allocations work, group membership, resource quotas. Explains -A/--account flag usage.

### **[University Medical Center Utrecht](https://www.umcutrecht.nl)**

#### Division Biomedical

#### Division Cardiology & Pulmonology

#### Division Imaging

#### Division Internal Medicine

#### Julius Center

#### Division Laboratories & Pharmacy

#### Division Neuroscience

### **[Utrecht University](https://www.uu.nl)**

#### Science Faculty, Department of Information and Computing Sciences

#### Science Faculty, Department of Biology

### **[Hubrecht Institute](https://www.hubrecht.eu/nl/)**

### **[Princess Máxima Center for Pediatric Oncology](https://www.prinsesmaximacentrum.nl/nl)**


---

# Data Management

## Transferring Data

> **Summary:** Data transfer methods: scp, rsync, SFTP (via MobaXterm), Globus, SURFfilesender for large files. Internal paths, external transfer via gateway. Covers efficient large-dataset transfers.

For transferring data to and from the HPC, two transfer nodes have been configured: hpct04.op.umcutrecht.nl and hpct05.op.umcutrecht.nl. 
Both machines have a much higher bandwidth than the login/submission server (20Gb/s versus 2Gb/s), so please use these for regular (large) data transfers.

You can use (for example) sftp or rsync to push or pull your data to and from the HPC from you local workstation. You can login on these machines using ssh, as described for the login server. For regular data transfers, you can create a cronjob that runs on scheduled intervals and copies (or synchronizes) certain data files or directories.

In MS-Windows you can use the tools [**WinSCP**](https://winscp.net/eng/download.php) or the sftp in [**Mobaxterm**](http://mobaxterm.mobatek.net/download-home-edition.html). 
*This software is also available in the "UMC digital desktop".* 
In this graphical software you can configure "the secure filecopy" with the gateway and hop directly to hpcs05 / hpcs06. (if desired).

When using linux you can install [**filezilla**](https://filezilla-project.org/) for a scp gui. 
You can configure a tunnel trough the gateway by creating an entry in your ~/.ssh/config file with these lines:



Host gwhpcs05 
  HostName hpcgw.op.umcutrecht.nl 
  User myusername 
  IdentityFile ~/.ssh/id_ed25519_hpc 
  LocalForward 8888 hpcs05.op.umcutrecht.nl:22 
  ForwardX11 yes



activate this connection by : 
ssh gwhpcs05 
Enter with **passphrase **of your key

Configure now a ='filezilla site-config' = (File / Site Manager) =\> New site with Protocol: 'sftp' ; Host on **localhost** port 8888 and push **connect**.

For big data file-transfer you can also use :

1. surfdrive [http://www.surfdrive.surf.nl/](http://www.surfdrive.surf.nl/)
2. or surffilesender [https://www.surffilesender.nl](https://www.surffilesender.nl)
3. or globus [https://www.globus.org/#transfer](https://www.globus.org/#transfer)

## Transferring Data on your local workstation using rsync and ssh (Linux, Mac, Mobaxterm)

substitute myusername by your own HPC username 
substitute mygroupname by your own HPC groupname

**- Create a secret/public-key file with a selfmade "passphrase" *(or use an existing key)***



ssh-keygen -f ~/.ssh/id_ed25519_hpc -t ed25519 -C HPC



Save with a strong passphrase and mail the file named ***id\_*ed25519*\_hpc.pub*** to <hpcsupport@umcutrecht.nl> 
**- Create a stanza in ~/.ssh/config**



Host hpcgw 
  HostName hpcgw.op.umcutrecht.nl 
  User myusername 
  IdentityFile ~/.ssh/id_ed25519_hpc

Host gw2hpct04 
  HostName hpct04.op.umcutrecht.nl 
  User myusername 
  Proxyjump hpcgw



Now you can use this command to rsync your data from- and to- the HPC inside your ssh session by entering :

From the HPC in **/hpc/my_group/myusername/data** to your local workstation in **/tmp/data_from_HPC** .



/usr/bin/rsync -av -e "ssh -v -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" --progress gw2hpct04:/hpc/my_group/myusername/data /tmp/data_from_HPC



(enter your passphrase and then your password) 
**OR** 
From **local workstation** to the **HPC** by :



/usr/bin/rsync -av -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" --progress /tmp/data_to_HPC gw2hpct04:/hpc/my_group/myusername/data/



(enter your passphrase and then your password)

## iRODS

> **Summary:** iRODS data management system: icommands (iput, iget, ils), metadata, data policies. Integration with HPC workflows for managed research data.

## Irods Information

The [irods commandline client](https://irods.org/) software is installed on the **Transfer-nodes** in the ***hpct04*** and ***hpct05*** servers of the HPC. 
On these transfer servers you can up and download software to and from the irods-server of the UU. 
Therefore you can use iget or iput commands. 
see **man ipu**t or **man iget** for more information.

1. login to the HPC
2. goto hpct04.op.umcutrecht.nl or hpct05.op.umcutrecht.nl with ssh
3. use iput or iget files
4. p.e. iget -v -f mytestfile.txt .
5. p.e. iput -v -f mytestfile.txt

see more info :

1. ienv
2. iuserinfo


---

# Additional Resources

## Open OnDemand

> **Summary:** Web portal access: https://hpcs05.op.umcutrecht.nl or hpcs06. Features: file browser, job composer, interactive apps. Requires UMC network or VPN (vdi-ext.umcutrecht.nl, solisworkspace.uu.nl).

Open OnDemand provides graphical access to the HPC cluster via web browser. Access is restricted to on-network connections at Hubrecht, PMC, and UMCU for security reasons. 

### Access Instructions

Direct access requires an **institute network connection** at Hubrecht, PMC, or UMCU. Use one of these URLs:

[https://hpcs05.op.umcutrecht.nl](https://hpcs05.op.umcutrecht.nl%20)    
[https://hpcs06.op.umcutrecht.nl ](https://hpcs06.op.umcutrecht.nl%20)

Login with your username and password

### Remote access

- UMCU affiliated users can enable JAMF-Trust on a UMC managed workstation or use a webbrowser on a virtual workstation using <https://vdi-ext.umcutrecht.nl/portal/>
- UU affiliated users can use a web browser on a virtual workstation here: <https://solisworkspace.uu.nl>

### Available Apps

- Jupyter notebook (requires Jupyter available in your PATH, for example in a base [Miniforge Conda environment](#conda))
- Linux Desktop (XFCE)
- [RStudio Server](#rstudio-server)

## RStudio Server

> **Summary:** RStudio via Open OnDemand: launching sessions, resource allocation, package installation in user library. Alternative to command-line R.

Select Rstudio server from the Interactive apps menu:

![1764862827444-307.png](../../../../../attachment/xwiki/Main/Open+Ondemand/Rstudio+Server/WebHome/1764862827444-307.png)

This open a page with a form to fill as shown below. Please note:

- Do not set your home folder as working directory because it can exceed the space available there.
- A subfolder is created in the working directory for additional packagesin \<working directory\>/R/rocker-rstudio/\<R-version\>

![1764862860184-644.png](../../../../../attachment/xwiki/Main/Open+Ondemand/Rstudio+Server/WebHome/1764862860184-644.png)

After clicking the launch button a job is queued to start the server.

![1764862878826-789.png](../../../../../attachment/xwiki/Main/Open+Ondemand/Rstudio+Server/WebHome/1764862878826-789.png)

Once a node is assigned, the status is changed to Starting. The initial startup can take up to 15 minutes to fetch the container and start the server

![1764865858483-201.png](../../../../../attachment/xwiki/Main/Open+Ondemand/Rstudio+Server/WebHome/1764865858483-201.png)

After status changes to Running you can click the ‘Connect button’ to open Rstudio server in new tab of your browser. Click cancel on the card to end the session, closing the browser tab with Rstudio server will not stop the session.

![1764862893441-385.png](../../../../../attachment/xwiki/Main/Open+Ondemand/Rstudio+Server/WebHome/1764862893441-385.png)

## Cromwell Workflow Engine

> **Summary:** WDL workflow execution: Cromwell server setup, workflow submission API, job monitoring, SLURM backend configuration. Covers multi-step bioinformatics pipelines.

Cromwell is a workflow management system geared towards scientific workflows. More information can be found [online](https://cromwell.readthedocs.io/).

It can function as a workflow-execution engine that can parse jobs written in the workflow-definition language [WDL](https://github.com/openwdl/wdl/blob/master/versions/draft-2/SPEC.md#introduction) and execute them on a range of different backends. 
This makes workflows written in WDL easier to share, easier to migrate and opens up the usage of pipelines developed elsewhere. 
In addition, Cromwell remembers each subtask input and output and repeats only the tasks it needs to; reusing output of previously run tasks. 
This can be of great benefit when your 30-step analysis pipeline crashed at step 29!

## HPC Cromwell-as-a-service (CaaS)

The HPC team has setup a Cromwell-as-a-service. This (CaaS) is serviced from a dedicated server running a separate Cromwell-service instance per user. 
A user can then post jobs to a provided URL of his/her personal instance. A posted job (or workflow) will then be processed on the HPC in the users’s name. 
A user will need to explicitly request access to the service for it is quite a waste to have one for each user by default; not everyone will use the service. 
The (CaaS) is secured by a Basic Authentication with a custom username / password. When posting a job to the (CaaS) you need to submit these credentials.

Before you request usage of the (CaaS) we kindly request you to quickly scan the [Cromwell documentation](https://cromwell.readthedocs.io/). 
We especially recommend the very short [5-minute introduction to Cromwell](https://cromwell.readthedocs.io/en/stable/tutorials/FiveMinuteIntro/) to get a feel for what Cromwell can do. 
Please note that within the introduction it refers to running Cromwell in Run mode whereas the (CaaS) runs Cromwell in Server mode. Server mode has a slightly shorter [introduction](https://cromwell.readthedocs.io/en/stable/tutorials/ServerMode/). 
Because (CaaS) is about running Cromwell as a service with a REST interface, reading about [Cromwell Server REST API](https://cromwell.readthedocs.io/en/stable/api/RESTAPI/) is crucial.

## Apply for the service

If you want to request a (personal) Cromwell service, send an e-mail to <HPCSupport@umcutrecht.nl> with:

## Required information

1. A HPC username of user (e.g. johndoe)
2. A secure way to share the password(s) with you (i.e. mobile-phone number)
3. An existing workflow-execution directory (i.e. /hpc/institute or group/johndoe/cromwell-executions), accessible from a HPC compute node and writable to the user
4. An existing workflow-log directory (i.e. /hpc/group/johndoe/cromwell-logs), accessible from a HPC compute node and writable to the user

## Optional information

1. The version of Cromwell the (CaaS) needs to run for you (default: the *latest* configured)
2. Username of a read-only account; a secondary user account for the (CaaS) instance that can only do GETs but not POST new jobs on the REST service (default: none)

## Example: job submission

A workflow can be submitted to the [RESTful API endpoints](https://cromwell.readthedocs.io/en/stable/api/RESTAPI/#cromwell-server-rest-api) of the Cromwell service. These endpoints are prefixed by the URL of a Cromwell service (e.g. *johndoe.hpccw.op.umcutrecht.nl*). 
As is the nature of RESTful APIs this can be done in many different ways. One such way is using the widely-available command-line interface command cURL.

Below is an example where hello.wdl is the workflow, name.json is the input for the workflow, and johndoe is the user:



\$ curl -X POST "[https://johndoe.hpccw.op.umcutrecht.nl/api/workflows/v1](https://johndoe.hpccw.op.umcutrecht.nl/api/workflows/v1)" \\ 
   --user johndoe:password1 \\ 
   --header "accept: application/json" \\ 
   --header "Content-Type: multipart/form-data" \\ 
   --form "workflowSource=@hello.wdl" \\ 
   --form "workflowInputs=@name.json"



This should then output:



    "id":"3415ad29-ecc0-4a9d-93e2-660d0a95945d", 
    "status":"Submitted"



Which tells us that the job is been successfully submitted to Cromwell and has been given the id **3415ad29-ecc0-4a9d-93e2-660d0a95945d**.

Cromwell will pick up the job and start to execute each of the tasks in the workflow on a submit node of the HPC.

Keeping tabs on the progression of the workflow can be done via 
the [RESTful endpoints](https://cromwell.readthedocs.io/en/stable/api/RESTAPI/#cromwell-server-rest-api) status/timing/metadata in combination with the the id of the job. 
For instance : visiting** https://johndoe.hpccw.op.umcutrecht.nl/api/workflows/v1/3415ad29-ecc0-4a9d-93e2-660d0a95945d/status **in the browser will output:



    "status": "Succeeded", 
    "id": "3415ad29-ecc0-4a9d-93e2-660d0a95945d"



And tells you that the workflow succeeded; which entails it successfully finished.

Aborting a running workflow is also facilitated by a [RESTful endpoint](https://cromwell.readthedocs.io/en/stable/api/RESTAPI/#cromwell-server-rest-api) abort in combination with the id of the job. 
For instance; running 



curl -X POST <https://johndoe.hpccw.op.umcutrecht.nl/api/workflows/v1/3415ad29-ecc0-4a9d-93e2-660d0a95945d/abort> 



in a terminal will output:



  "status": "Aborted", 
  "id": "3415ad29-ecc0-4a9d-93e2-660d0a95945d"



## Alternative submissions tools

Doing every submission via cURL can be bothersome. 
Nearly all popular programming languages have packages or support for calling RESTful APIs (e.g. Python:*requests*, R:*RCurl*. 
However, there are several Cromwell specific alternatives.

## Swagger UI

Simply visiting https://johndoe.hpccw.op.umcutrecht.nl in a browser will provide you with a Swagger user interface that can aid in building and test cURL-like calls to the Cromwell service.

## Python package: cromwell-tools

Broad institute has also developed a [Python package](https://github.com/broadinstitute/cromwell-tools) to interact with Cromwell. 
This package can also be used via the command-line interface.



\$ cromwell-tools submit --username johndoe --password password1 --url [https://johndoe.hpccw.op.umcutrecht.nl](https://johndoe.hpccw.op.umcutrecht.nl) -w hello.wdl -i name.json



## **Technical details**

## Caching heuristics

Having each Cromwell service calculate a md5 checksum over multiple files puts a considerable load on the input/output throughput of the HPC storage. As such, Cromwell is configured to use "path+modtime" instead of "file" as caching heuristic. More information can be found in [cromwell.readthedocs.io](https://cromwell.readthedocs.io/en/stable/Configuring/#call-caching). 
In short, do not modify any input files and then manually reset the modtime on those files. 

Silly you if you do.

### Outside access to the (CaaS)

The URL of the Cromwell service (i.e. https://johndoe.hpccw.op.umcutrecht.nl) can only be accessed from within permitted domains. The UMC domain is permitted by default. It is possible to permit access from a different domain; please contact <HPCSupport@umcutrecht.nl> and provide a source IP address.

### Configuration

To reduce administrative load for the HPC team only a single configuration exists for all Cromwell services of a specific version. These are provided by the Kemmeren group in Princess Máxima Center and are a result of years of experience with Cromwell. The configurations are hosted on [bitbucket](https://bitbucket.org/princessmaximacenter/cromwell-configs).

### WDL version

At the time of writing the WDLs submitted to the Cromwell service are by default expected to be in draft-2 of the WDL specifications. You can override this via [workflow options](https://cromwell.readthedocs.io/en/stable/wf_options/Overview/#workflow-options-overview).

## HowToS

## Backup a (CaaS) database

By default your (CaaS) database with the workflow cache and metadata is NOT backed up. It is possible to set this up yourself; access to the MySQL database is provided.

1. Login to one of the HPC transfer nodes 
 \$ ssh johndoe@hpct03.op.umcutrecht.nl



1. Create a directory to hold MySQL configurations and securely set the permissions 
 \$ mkdir /.mysql && chmod 0700 /.mysql



1. Create a file backup-caas-johndoe.cnf with the following content (note the slightly abnormal *host*!): 
 \[mysqldump\] 
  user=johndoe 
  password=password1 
  host=johndoe.hpccw03.compute.hpc



1. Test-run creating a backup using mysqldump 
 \$ module load mysql; mysqldump --defaults-extra-file=/.mysql/backup-caas-johndoe.cnf johndoe \| gzip -9 \> johndoe-backup\_\`date "+\\F\_\\H\\M"\`.sql.gz' 
  
2. Create a cronjob (i.e. a command that is executed [periodically](https://crontab-generator.org/)) to do this backup for you. 
 Note that you might want to specify a target directory. For instance, have it every Sunday at 5am: 
 \$ command='module load mysql; mysqldump --defaults-extra-file=/.mysql/backup-caas-johndoe.cnf johndoe \| gzip -9 \> /data/isi/g/group/johndoe-backup\_\`date "+\\F\_\\H\\M"\`.sql.gz'; \$ (crontab -l ; echo "0 5 \* \* SUN bash -l -c '\$command'") \| crontab -

## Restore a (CaaS) database

Restoring a (gzipped) database dump can be done as follows 1. Login to one of the HPC transfer nodes 
\$ ssh johndoe@hpct03.op.umcutrecht.nl

1\. Unpack the backup while redirecting it to the mysql client 
**\$ gunzip \< johndoe-backup.sql.gz \| mysql --user=johndoe --password --host=johndoe.hpccw03.compute.hpc johndoe**

## Connect to the (CaaS) via the HPC gateway

The permitted-domain security of the (CaaS) can be circumvented in a slightly convoluted way by use of a SSH-proxy jump via the HPC gateway with the addition of a port forward:



\$ ssh -L 4242:johndoe.hpccw.op.umcutrecht.nl:443 \\ 
  -l johndoe \\ 
  -o ProxyCommand='ssh -q %r@hpcgw.op.umcutrecht.nl -W %h:%p' \\ 
  hpcsubmit.op.umcutrecht.nl



If you then communicate with a RESTful endpoint you NEED to communicate with URL **https://localhost:4242** (note the http*s*) instead of **https://johndoe.hpccw.op.umcutrecht.nl** , 
set the Host header for the HTTP request, 
and allow for insecure connections:



\$ curl [https://localhost:4242/api/workflows/v1/backends](https://localhost:4242/api/workflows/v1/backends) \\ 
  --insecure \\ 
  --user johndoe:password1 \\ 
  --header "Host: johndoe.hpccw.op.umcutrecht.nl"



## WDL examples

Below are the content of the files that are used in the examples above. 
A full WDL specification can be found at [https://github.com/openwdl/wdl/blob/master/versions/draft-2/SPEC.md#introduction](https://github.com/openwdl/wdl/blob/master/versions/draft-2/SPEC.md#introduction).

## file: hello.wdl



task hello { 
  String name

  command { 
    echo 'Hello \${name}!' 
  } 
  output { 
    File response = stdout() 
  } 
}

workflow test { 
  call hello 
}



### file: name.json

{ "test.hello.name": "World" }

## Do's and Don'ts

> **Summary:** Cluster etiquette: don't run on login nodes, don't hog resources, do use scratch for temp files, do clean up. Policy violations and consequences.

1. Do : **use array jobs **for multi-job pipelines
2. Do : Keep your HPC password in a digital safe p.e [https://keepass.info/](https://keepass.info/)



1. Don't : **tar / untar / zip or unzip** on the transferhost or submithosts ( please use compute-nodes )
2. Don't : **use dropbox **(dropbox because it is too insecure)
3. Don't run jobs on the **submit-nodes** *hpcs05* or *hpcs06* but use the **compute-nodes** (sbatch/srun)

## External Links

> **Summary:** Curated external resources: SLURM docs (slurm.schedmd.com), shell tools (shellcheck, explainshell), language tutorials, Apptainer/Docker docs.

| Info |  URL |
|----|----|
| Bash |  [shellcheck](https://www.shellcheck.net) |
|   |  [explainshell](https://explainshell.com)   |
|   |  [Linux-for-beginners](https://www.freecodecamp.org/news/bash-scripting-tutorial-linux-shell-script-and-command-line-for-beginners) |
| Docker-virtualisation |  [Docker-info](https://docs.docker.com/desktop/) |
| HTML |  [html-info](https://www.w3schools.com/html) |
| Java |  [java-info](https://www.w3schools.com/java) |
| Java_script |  [javascript-info](https://www.w3schools.com/js) |
| Open Ondemand |  [ondemand](https://osc.github.io/ood-documentation/latest/) |
| Python |  [python-info](https://www.w3schools.com/python) |
| R |  [R-info](https://www.w3schools.com/r) |
| Rocky Linux  |  [rockylinux](https://rockylinux.org) |
| Apptainer-virtualisation  |  [Apptainer](https://apptainer.org/docs/user/latest/) |
| Slurm |  [slurm-schedular](https://slurm.schedmd.com) |
| UMC |  [powerpoint slurm-schedular](https://wiki.bioinformatics.umcutrecht.nl/pub/HPC/WebHome/HPC_user_counsil_20200303.pptx) |

## Conditions of Use

> **Summary:** Usage policy: acceptable use, data handling requirements, security obligations, account responsibilities. Required reading for compliance.

## Conditions and Support

In order to be able to use the HPC facility, you need to be affiliated with University Medical Center Utrecht, Utrecht University, Hubrecht Institute or Princess Maxima Center for pediatric oncology. This means that you either need to be employed by one of these institutes or you need to have a "gastvrijheidsverklaring". The responsibility to ensure that this is the case is up to the principal investigator of the individual research groups locate in one of these institutes.

By using the HPC facility you also comply with the following policies:

- You are familiar with the guidelines of scientific conduct set forth by UMC Utrecht, Utrecht University, Hubrecht Institute or Princess Maxima Center.
- If applicable, you are familiar with and comply with the latest legislation concerning patient-related research.
- Patient-related research data are not allowed on the HPC infrastructure. However, if the data has been (pseudeo)anonymized beforehand, so that samples cannot be traced back to individual subjects, you can use this data on the HPC infrastructure.
- Abuse of HPC infrastructure resources may result in termination of the user account.

## Support

Support for the HPC facility is provided on a "best effort" basis. This means that we will do our utmost best to keep the infrastructure running at all times, but that we cannot and will not guarantee 100% up time and do not have 24/7 support. Support requests are taken care of during normal working hours (weekdays, 9.00-17.00) and you can expect us to reply within a day. During weekends and evenings, we do typically monitor support requests and respond if possible, but this depends heavily on the availability and willingness of our support team to do this during their free time. No guarantees about response times will be given and/or can be claimed about support requests made during the weekend or evening. If not handled during this period, they will be taken care of the next working day.

Support requests should be directed to <hpcsupport@umcutrecht.nl>, only then can we guarantee that we are able to provide the support as indicated here.

To avoid confusion, we also want to be clear on what we support:

- Hardware support for compute nodes if a valid hardware support contract with the hardware supplier is in place.
- General Operating System maintenance (security updates, software fixes, monitoring and management).
- Configuration, optimization, maintenance and monitoring of the queueing engine and available resources.
- Configuration, optimization, maintenance and monitoring of the HPC storage system.
- Configuration, optimization, maintenance and monitoring of the HPC submit hosts and master hosts.

In addition, we try to assist/advise on the following topics, but cannot guarantee that we are able to provide a solution:

- Compilation, installation and configuration of group-specific software packages.
- Resolve simultaneous peak performance needs of different groups.
- Implementation, configuration and optimization of bioinformatics workflows/pipelines.

## Your Privacy

The European General Data Protection Regulation (GDPR) (Dutch: Algemene Verordening Gegevensbescherming) requires us to disclose the information that we gather about you, what we use it for, and for how long we store this information. Please note that under the GDPR, you have certain additional rights (the right to see the information we have about you, the right to be forgotten, etcetera). We invite you to read the GDPR, and if you want to exercise any of these rights, please let us know (<hpcsupport@umcutrecht.nl>) and we'll help you to the best of our abilities.

The HPC facility falls under the jurisdiction of the UMC Utrecht, so all the terms and regulations that are listed in the UMC Utrecht privacy statement (URL not known yet, will be added later) apply to us as well. Below, we will outline what we specifically, as HPC, gather and store about you.

## Some personal information

The HPC user database contains your name, your e-mail address, and in some cases your telephone number. We need your e-mail address to be able to inform you about current affairs (e.g., planned downtime). We use the telephone number to be able to contact you for urgent incidents (e.g., anomalous use of the system, suspected account abuse). We keep this data for as long as your account is active, and a maximum of 6 months after that. After this period, your personal data will be removed from the account. The account itself is kept, in a disabled state, because not all your files are removed (see below), and they need an owner.

## Your files

The HPC is not a place to store "personal" files. We expect your files to contain work-related material only.

File security is based on the standard Unix filesystem security, in which the "owner", the "group" and "others" can have certain permissions (read/write/execute). By default, these permissions will be set to a secure state (see below). Note that the HPC administrators have the ability to read/write/execute your files, but will not do so without your permission.

There are several places to store your HPC files.

- Your homedirectory, which by default is only readable by you. Other users cannot read this directory, unless you set more permissive permissions yourself. This directory will be removed 6 months after your HPC account is deactivated. It should contain things like login-scripts, personal configuration files, etc.



- Several group directories (/hpc/local, /hpc/shared, /hpc/groupname). By default, these locations are readable by the other members of your group, but are not accessible by people in other groups. Files and directories you create here should contain the majority of your research data. These files and directories will not be removed after your account has been disabled, as they may be relevant for other group members.

## Login data

When you log in to our systems, we store the time that you log in and out, and the IP address you came from. We keep this information for 6 months.

We need this information to monitor account usage, and to be able to detect anomalous logins: "This person is suddenly logging in from several places around the globe; perhaps the account is hacked".

## Job data

For every HPC job you submit, some data is stored in our database. Most information is purely technical (which node did it run on, what is the job number, how much CPU and memory did it use), and some information could be construed to be personally identifiable.

These are: your username, the group you submitted the job for, the submission time, and the job name.

The data gathered about user jobs is basically the core register of the HPC system. We need it to monitor, diagnose, and predict how our groups are using our system, for billing and capacity planning. Therefore, we keep this data for no less than 7 years.

## Contact

> **Summary:** Support contacts: hpcsupport@umcutrecht.nl for technical issues, account requests, access problems. Escalation paths.

## Initial contact

Initial intakes for new research groups and general information about the HPC facility are handled by **Ies Nijman** and **Jeroen de Ridder**.

Please contact them about these topics. 
email: <J.deRidder-4@umcutrecht.nl> \| University Medical Center Utrecht - Center for Molecular Medicine \| Universiteitsweg 100, STR 1.305 \| 3584 CG Utrecht, The Netherlands \| 31 (0)88 7550406 \| 
or 
email: [INijman@umcutrecht.nl](mailto:J.deRidder-4@umcutrecht.nl) \| University Medical Center Utrecht - Center for Molecular Medicine \| Universiteitsweg 100, STR 1.305 \| 3584 CG Utrecht, The Netherlands \| 31 (0)88 7550406 \|

## User questions

If you already are using the HPC facility and have specific questions? We encourage you to send an email to the following general address. 
Emails will be read by the HPC system administrators. The level of support we can provide is indicated at [ConditionsAndSupport](#conditions-of-use). 
email: <hpcsupport@umcutrecht.nl>

## HPC team

[ Ies Nijman (manager)  ](mailto:i.nijman@umcutrecht.nl) 
[ Jeroen de Ridder (manager)   ](mailto:j.deridder-4@umcutrecht.nl) 
[ Martin Marinus  ](mailto:m.marinus@umcutrecht.nl) 
[ Jacob Baggerman  ](mailto:j.baggerman@umcutrecht.nl)


---

*End of HPC Cluster Documentation*
