# -*- coding: utf-8 -*-

import torchvision
import torch
import pickle
import matplotlib.pyplot as plt
import os

# setup device (CPU/GPU)
if torch.cuda.is_available():
    device = torch.device('cuda:1')
else:
    device = torch.device('cpu')
# device = torch.device('cpu')

print(f"Working on device: {device}.")

dataset_name = "imagenet"
datapath = os.path.join("data", dataset_name)
basepath = os.path.join("")

# from dataset_management.task_creation import construct_tasks
# construct_tasks(datapath, min_imgs = 450, max_imgs = 800)

"""## **Datasets** """

from dataset_management.dataset_creation import TinyImagenetTask
from dataset_management.dataset_creation import get_cl_dset

"""### Getting the datasets"""
# cl_dset = get_cl_dset(os.path.join(datapath, "cl_t7_c21.txt"))
# cl_dset = get_cl_dset(os.path.join(datapath, "cl_t5_c15.txt"))
"""
cl_dset: a dictionary containing
        -> key 'meta': dict with keys: cls_no (classes per task), task_no (# of tasks), misc (number of misc classes)
        -> other keys: the disjoint superclasses used in making of tasks (their number is the number of classes/task)
"""
split_file_name = "cl_t7_c21.txt"
cl_dset = get_cl_dset(os.path.join(datapath, split_file_name))

def make_datasets(cl_dset, datapath, randomise = False, show_dataset_task_sample = False):
    from dataset_management.dataset_creation import get_task

    all_classes = list()
    for task_no in range(cl_dset['meta']['task_no']):
        print(f"Showing info for task {task_no}")
        task = get_task(cl_dset, task_no, datapath, verbose=False)  # list of classes corresponding to task
        all_classes += task
    if randomise:
        from random import shuffle
        shuffle(all_classes)
    datasets = list()
    for task_no in range(cl_dset['meta']['task_no']):
        task = all_classes[task_no * cl_dset['meta']['cls_no']:(task_no + 1) * cl_dset['meta']['cls_no']]
        dset_task = TinyImagenetTask(os.path.join(datapath, "train"), task,
                            transform = torchvision.transforms.Compose([
                                torchvision.transforms.ToTensor(),
                                torchvision.transforms.Resize((300,300)),
                                torchvision.transforms.RandomHorizontalFlip(p=0.5),
                                torchvision.transforms.RandomVerticalFlip(p=0.5),
                                torchvision.transforms.RandomRotation((-90,90)), #min and max degrees
                                torchvision.transforms.GaussianBlur(kernel_size = (1,1), sigma=(0.1, 2.0)),
                                torchvision.transforms.RandomErasing(p=0.5, scale=(0.02, 0.25), ratio=(0.3, 3.3)),
                                torchvision.transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
                              ])
                            )
        datasets.append(dset_task)
        im, label = dset_task[0]
        if task_no == 0:
            print(f"We have images of shape {im.shape}")
        if show_dataset_task_sample:
            #(task loaded, showing 10 imgs from task)
            print(f"\n\n Showing 10 images from the dataset of task {task_no}.")
            print(dset_task._subset)
            fig = plt.figure()
            axes = fig.subplots(2, 5)
            for i in range(10):
              im, label = dset_task[i]
              axes[i//5, i%5].set_title(f"label: {label}")
              axes[i//5, i%5].imshow(im.permute(1,2,0))
            fig.set_figheight(5)
            fig.set_figwidth(5)
            fig.suptitle(f"Dataset {task_no}")
            fig.tight_layout()
            plt.show(block = False)
            print("\n\n")
    return datasets


datasets = make_datasets(cl_dset, datapath, randomise = False)
baseline_datasets = make_datasets(cl_dset, datapath, randomise = True)


##Training

"""Choose model to be used"""

def get_model(model_type):
  if model_type == "LeNet":
    from Models import LeNet
    model = LeNet()
  elif model_type == "LeNet5":
    from Models import LeNet5
    model = LeNet5()
  elif model_type == "ModDenseNet":
    from Models import ModDenseNet
    from Models import Block
    model = ModDenseNet(block = Block, image_channels = 3, num_classes = cl_dset['meta']['cls_no'], device = device)
  elif "Resnet" in model_type:
    if model_type == "Resnet152":
      model = torchvision.models.resnet152(pretrained=False)
    elif model_type == "Resnet101":
      model = torchvision.models.resnet101(pretrained=False)
    elif model_type == "Resnet50":
      model = torchvision.models.resnet50(pretrained=False)
    elif model_type == "Resnet18":
      model = torchvision.models.resnet18(pretrained=False)
    elif model_type == "Densenet169":
      model = torchvision.models.densenet169(pretrained=False)
    elif model_type == "Densenet201":
      model = torchvision.models.densenet201(pretrained=False)
    model.fc = torch.nn.Sequential(
              torch.nn.Linear(in_features = model.fc.in_features, out_features = model.fc.in_features//4, bias = True), #was initially /2 -> /4 -> /8
              torch.nn.ReLU(),
              torch.nn.Linear(in_features = model.fc.in_features//4, out_features = model.fc.in_features//8, bias = True), 
              torch.nn.ReLU(),
              torch.nn.Linear(in_features = model.fc.in_features//8, out_features = cl_dset['meta']['cls_no'], bias = True)
            )
  return model

#@title Choose model


model_type = "Resnet101" #@param ["LeNet", "LeNet5", "Resnet101", "Resnet50", "Resnet18", "Resnet152", "Densenet169", "Densenet201", "ModDenseNet"]
model = get_model(model_type)

get_back = False
if get_back:
    model.load_state_dict(torch.load(os.path.join(basepath,"savedump",
                        f"{model.__class__.__name__}_{str(trainer.num_epochs)}_epochs_lr{str(trainer.lr)}_model_after_task{str(task_no)}")))


#auxiliary

trainer_params = {
    "batch_size": 20,
    "num_epochs": 30,
    "learning_algo": "adam",
    "learning_rate": 1e-3,
    "weight_decay": 1e-5,
    "device": device,
    "basepath": basepath
}

from Trainer import Trainer

trainer = Trainer(model, trainer_params)

"""###Training for each task, all in a loop over tasks

Training on separate tasks:

Structure of metrics dictionary:
four entries (train & test loss, train & test acc),
each a list of lists:
for task i, the list contains all losses on the previous tasks including the current one for each epoch.
"""

def train_datasets(model, trainer, datasets, basepath, save_on_the_way = True, save_appendix = "", start_from_task = 0):
  metrics = list()
  train_loaders, test_loaders = [], []
  fisher_diag = None
  prev_params = None
  for task_no in range(len(datasets)):
    trainer.task_no = task_no
    trainer.save_appendix = save_appendix
    dset_task = datasets[task_no]
    #split dataset for this task
    train_dset_task, test_dset_task = torch.utils.data.random_split(dset_task,[int(len(dset_task)*0.8),len(dset_task) - int(len(dset_task)*0.8)])

    #add data loaders corresponding to current task
    train_loaders.append(torch.utils.data.DataLoader(train_dset_task, batch_size=trainer.batch_size, shuffle=True, drop_last=False))
    test_loaders.append(torch.utils.data.DataLoader(test_dset_task, batch_size=trainer.batch_size, shuffle=True, drop_last=False))
    
    print(f"\n \n Finished processing dataset for task {task_no}. Proceeding to training.")
    #training (all tasks have the same # epochs and batch sizes)
    if task_no >= start_from_task:
        metrics_task, fisher_diag_task = trainer.train(train_loaders, test_loaders, prev_fisher = fisher_diag, prev_params = prev_params)
        metrics.append(metrics_task)

        #modify fisher diag to also reflect task that was trained on.
        if fisher_diag is None:
            fisher_diag = fisher_diag_task
        else:
            fisher_diag += fisher_diag_task

        #save params after task is done training
        """with torch.no_grad():
            for param in trainer.model.parameters():
                if prev_params is None:
                    prev_params = param.detach().clone().view([1, -1])
                else:
                    prev_params = torch.cat((prev_params, param.detach().clone().view([1, -1])), dim=1)"""
    if save_on_the_way and task_no >= start_from_task:
      import pickle
      with open(os.path.join(basepath, 'savedump',
                f"{model.__class__.__name__}_{str(trainer.num_epochs)}_epochs_metrics_task_{str(task_no)+save_appendix}"), 'wb') as filehandle:
        pickle.dump(metrics[-1], filehandle)
      torch.save(model.state_dict(), 
                os.path.join(basepath,'savedump',
                f"{model.__class__.__name__}_{str(trainer.num_epochs)}_epochs_model_after_task{str(task_no)}{save_appendix}") )
    # plot_metrics(metrics[task_no], title = f"Task {task_no} metrics after {trainer.num_epochs} epochs with learning rate {trainer.lr} for model {model.__class__.__name__}.")
    #RESETTING OPTIMIZER FOR BEGINNING OF NEW TASK
    if trainer_params['learning_algo'] == 'adam':
            trainer.optimizer = torch.optim.Adam(params = trainer.model.parameters(),
                                  lr = trainer_params['learning_rate'], weight_decay = trainer_params['weight_decay'])
    else:
            trainer.optimizer = torch.optim.SGD(params = trainer.model.parameters(), 
                                 lr = trainer_params['learning_rate'], weight_decay = trainer_params['weight_decay'])
  return metrics


if True:
    metrics = train_datasets(model, trainer, datasets, basepath, save_on_the_way = False, save_appendix = f"_{dataset_name}", start_from_task = 0)
    with open(os.path.join(basepath,'savedump',
        f"{model.__class__.__name__}_{str(trainer.num_epochs)}_epochs_lr{str(trainer.lr)}_overall_metrics_{dataset_name}"), 'wb') as filehandle:
          pickle.dump(metrics, filehandle)

    """Training on baseline dataset"""

    #@title Train on baseline (reinitialise model if it was already trained on nonbaseline tasks)
    reinitialise_model = False  #@param {type:"boolean"}
    if reinitialise_model:
      model = get_model(model_type)
    #MODEL & TRAINER MUST BE REINITIALISED IF ALREADY TRAINED ON GOOD TASKS
    metrics_baseline = train_datasets(model, trainer, basepath, baseline_datasets, save_on_the_way = True, save_appendix = f"_baseline_{dataset_name}")
    with open(os.path.join(basepath, "savedump",
                           f"{model.__class__.__name__}_{str(trainer.num_epochs)}_epochs_lr{str(trainer.lr)}_overall_metrics_baseline_{dataset_name}")
            , 'wb') as filehandle:
          pickle.dump(metrics_baseline, filehandle)

    """Training on big dataset"""
    #NOT NEEDED ANYMORE
    # def train_big_dset(model, trainer, datasets):#now train on a the whole dataset, of all tasks:
    #   big_dset = torch.utils.data.ConcatDataset(datasets)
    #   train_dset, test_dset = torch.utils.data.random_split(
    #       big_dset, [int(len(big_dset)*0.8), int(len(big_dset)*0.2)])
    #   #create data loaders
    #   train_loader = [torch.utils.data.DataLoader(train_dset, batch_size=trainer.batch_size, shuffle=True, drop_last=False)] #must be list (with one element in this case)
    #   test_loader = [torch.utils.data.DataLoader(test_dset, batch_size=trainer.batch_size, shuffle=True, drop_last=False)]
    #   metrics_big_dset = trainer.train(train_loader, test_loader)
    #   import pickle
    #   with open(basepath+"savedump/"+model.__class__.__name__+'_'+str(trainer.num_epochs)+'_epochs'+'_lr'+str(trainer.lr)+'_metrics_big_dset', 'wb') as filehandle:
    #     pickle.dump(metrics_big_dset, filehandle)
    #   torch.save(model.state_dict(),
    #               basepath+"savedump/"+model.__class__.__name__+'_'+str(trainer.num_epochs)+'_epochs'+'_lr'+str(trainer.lr)+'_model_after_big_dset')
    #
    #   plot_metrics(metrics_big_dset, title = f"Metrics for combined dataset for model {model.__class__.__name__}.")

