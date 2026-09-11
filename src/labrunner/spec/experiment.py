from dataclasses import dataclass
from typing import List, Dict, Any
import yaml
from pathlib import Path

from labrunner.spec.errors import SpecValidationError


@dataclass
class DatasetSpec:
    name: str
    identity: str


@dataclass
class SourceSpec:
    repository: str


@dataclass
class ResourcesSpec:
    accelerator: str
    gpus: int


@dataclass
class ExperimentSpec:
    schema_version: int
    name: str
    source: SourceSpec
    command: List[str]
    seed: int
    resources: ResourcesSpec
    datasets: List[DatasetSpec]


def parse_experiment_spec(yaml_path: Path) -> ExperimentSpec:
    """Parses and strictly validates an experiment specification."""
    with open(yaml_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SpecValidationError(f"Invalid YAML format: {e}")

    if not isinstance(data, dict):
        raise SpecValidationError("Root of YAML must be a dictionary")

    # Helper for strict typing
    def get_typed(obj: Dict[str, Any], key: str, expected_type: type, parent_path: str = "") -> Any:
        full_key = f"{parent_path}.{key}" if parent_path else key
        if key not in obj:
            raise SpecValidationError(f"Missing required field: {full_key}")
        val = obj[key]
        if type(val) is not expected_type:
            raise SpecValidationError(f"{full_key} must be of type {expected_type.__name__}; got type {type(val).__name__} ({val!r})")
        return val

    # schema_version
    schema_version = get_typed(data, 'schema_version', int)
    if schema_version != 1:
        raise SpecValidationError(f"Unsupported schema_version: {schema_version}")

    # name
    name = get_typed(data, 'name', str)
    if not name:
        raise SpecValidationError("name must not be empty")

    # source
    source_data = get_typed(data, 'source', dict)
    repo = get_typed(source_data, 'repository', str, 'source')
    source_spec = SourceSpec(repository=repo)

    # command
    command_data = get_typed(data, 'command', list)
    if not command_data:
        raise SpecValidationError("command must not be empty")
    for i, cmd in enumerate(command_data):
        if type(cmd) is not str:
            raise SpecValidationError(f"command[{i}] must be of type str; got type {type(cmd).__name__} ({cmd!r})")
    if not command_data:
         raise SpecValidationError("command must not be empty")

    # seed
    seed = get_typed(data, 'seed', int)
    if seed < 0 or seed > 4294967295:
        raise SpecValidationError(f"seed must be an unsigned 32-bit integer (0 <= seed <= 4294967295); got {seed}")

    # resources
    resources_data = get_typed(data, 'resources', dict)
    acc = get_typed(resources_data, 'accelerator', str, 'resources')
    gpus = get_typed(resources_data, 'gpus', int, 'resources')
    resources_spec = ResourcesSpec(accelerator=acc, gpus=gpus)

    # datasets
    datasets_data = get_typed(data, 'datasets', list)
    datasets_spec = []
    for i, ds in enumerate(datasets_data):
        if type(ds) is not dict:
            raise SpecValidationError(f"datasets[{i}] must be a dictionary")
        ds_name = get_typed(ds, 'name', str, f'datasets[{i}]')
        ds_identity = get_typed(ds, 'identity', str, f'datasets[{i}]')
        datasets_spec.append(DatasetSpec(name=ds_name, identity=ds_identity))

    # Reject unknown fields at the root (simple check)
    known_fields = {'schema_version', 'name', 'source', 'command', 'seed', 'resources', 'datasets'}
    unknown_fields = set(data.keys()) - known_fields
    if unknown_fields:
        raise SpecValidationError(f"Unknown fields found: {', '.join(unknown_fields)}")

    return ExperimentSpec(
        schema_version=schema_version,
        name=name,
        source=source_spec,
        command=command_data,
        seed=seed,
        resources=resources_spec,
        datasets=datasets_spec
    )
