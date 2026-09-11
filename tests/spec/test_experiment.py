import pytest
from pathlib import Path
from labrunner.spec.experiment import parse_experiment_spec, ExperimentSpec, DatasetSpec, SourceSpec, ResourcesSpec
from labrunner.spec.errors import SpecValidationError

def test_valid_experiment_spec(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline

source:
  repository: .

command:
  - python
  - train.py
  - --epochs
  - "100"

resources:
  accelerator: cuda
  gpus: 1

seed: 42

datasets:
  - name: cifar10
    identity: cifar10-v1
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    spec = parse_experiment_spec(spec_path)
    assert isinstance(spec, ExperimentSpec)
    assert spec.schema_version == 1
    assert spec.name == "resnet-baseline"
    assert spec.source.repository == "."
    assert spec.command == ["python", "train.py", "--epochs", "100"]
    assert spec.resources.accelerator == "cuda"
    assert spec.resources.gpus == 1
    assert spec.seed == 42
    assert len(spec.datasets) == 1
    assert spec.datasets[0].name == "cifar10"
    assert spec.datasets[0].identity == "cifar10-v1"

def test_strict_typing_coercion(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: "1"
seed: 42
datasets: []
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="resources.gpus must be of type int; got type str"):
        parse_experiment_spec(spec_path)

def test_missing_seed(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: 1
datasets: []
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="Missing required field: seed"):
        parse_experiment_spec(spec_path)

def test_invalid_seed_type(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: 1
seed: "42"
datasets: []
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="seed must be of type int"):
        parse_experiment_spec(spec_path)

def test_invalid_seed_range_negative(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: 1
seed: -1
datasets: []
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="seed must be an unsigned 32-bit integer"):
        parse_experiment_spec(spec_path)

def test_invalid_seed_range_large(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: 1
seed: 4294967296
datasets: []
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="seed must be an unsigned 32-bit integer"):
        parse_experiment_spec(spec_path)

def test_unknown_fields(tmp_path):
    yaml_content = """
schema_version: 1
name: resnet-baseline
source:
  repository: .
command:
  - python
resources:
  accelerator: cuda
  gpus: 1
seed: 42
datasets: []
typo_field: "hello"
"""
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml_content)

    with pytest.raises(SpecValidationError, match="Unknown fields found: typo_field"):
        parse_experiment_spec(spec_path)
