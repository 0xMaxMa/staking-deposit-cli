import os
import click
import json
from typing import (
    Any,
)

from eth_typing import HexAddress

from staking_deposit.credentials import (
    CredentialList,
)
from staking_deposit.utils.validation import (
    validate_bls_withdrawal_credentials,
    validate_bls_withdrawal_credentials_matching,
    validate_eth1_withdrawal_address,
    validate_int_range,
    verify_bls_to_execution_change_json,
)
from staking_deposit.utils.constants import (
    DEFAULT_BLS_TO_EXECUTION_CHANGES_FOLDER_NAME,
    MAX_DEPOSIT_AMOUNT,
)
from staking_deposit.utils.click import (
    captive_prompt_callback,
    choice_prompt_func,
    jit_option,
)
from staking_deposit.exceptions import ValidationError
from staking_deposit.utils.intl import (
    closest_match,
    load_text,
)
from staking_deposit.settings import (
    ALL_CHAINS,
    MAINNET,
    PRATER,
    get_chain_setting,
    get_devnet_chain_setting,
)
from .existing_mnemonic import (
    load_mnemonic_arguments_decorator,
)


def get_password(text: str) -> str:
    return click.prompt(text, hide_input=True, show_default=False, type=str)


FUNC_NAME = 'generate_bls_to_execution_change'


@click.command()
@jit_option(
    default=os.getcwd(),
    help=lambda: load_text(['arg_bls_to_execution_changes_folder', 'help'], func=FUNC_NAME),
    param_decls='--bls_to_execution_changes_folder',
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@jit_option(
    callback=captive_prompt_callback(
        lambda x: closest_match(x, list(ALL_CHAINS.keys())),
        choice_prompt_func(
            lambda: load_text(['arg_chain', 'prompt'], func=FUNC_NAME),
            list(ALL_CHAINS.keys())
        ),
    ),
    default=MAINNET,
    help=lambda: load_text(['arg_chain', 'help'], func=FUNC_NAME),
    param_decls='--chain',
    prompt=choice_prompt_func(
        lambda: load_text(['arg_chain', 'prompt'], func=FUNC_NAME),
        # Since `prater` is alias of `goerli`, do not show `prater` in the prompt message.
        list(key for key in ALL_CHAINS.keys() if key != PRATER)
    ),
)
@load_mnemonic_arguments_decorator
@jit_option(
    callback=captive_prompt_callback(
        lambda num: validate_int_range(num, 0, 2**32),
        lambda: load_text(['arg_validator_start_index', 'prompt'], func=FUNC_NAME),
    ),
    default=0,
    help=lambda: load_text(['arg_validator_start_index', 'help'], func=FUNC_NAME),
    param_decls="--validator_start_index",
    prompt=lambda: load_text(['arg_validator_start_index', 'prompt'], func=FUNC_NAME),
)
@jit_option(
    callback=captive_prompt_callback(
        lambda num: validate_int_range(num, 0, 2**32),
        lambda: load_text(['arg_validator_index', 'prompt'], func=FUNC_NAME),
    ),
    help=lambda: load_text(['arg_validator_index', 'help'], func=FUNC_NAME),
    param_decls='--validator_index',
    prompt=lambda: load_text(['arg_validator_index', 'prompt'], func=FUNC_NAME),
)
@jit_option(
    callback=captive_prompt_callback(
        lambda bls_withdrawal_credentials: validate_bls_withdrawal_credentials(bls_withdrawal_credentials),
        lambda: load_text(['arg_bls_withdrawal_credentials', 'prompt'], func=FUNC_NAME),
    ),
    help=lambda: load_text(['arg_bls_withdrawal_credentials', 'help'], func=FUNC_NAME),
    param_decls='--bls_withdrawal_credentials',
    prompt=lambda: load_text(['arg_bls_withdrawal_credentials', 'prompt'], func=FUNC_NAME),
)
@jit_option(
    callback=captive_prompt_callback(
        lambda address: validate_eth1_withdrawal_address(None, None, address),
        lambda: load_text(['arg_execution_address', 'prompt'], func=FUNC_NAME),
    ),
    help=lambda: load_text(['arg_execution_address', 'help'], func=FUNC_NAME),
    param_decls='--execution_address',
    prompt=lambda: load_text(['arg_execution_address', 'prompt'], func=FUNC_NAME),
)
@jit_option(
    # Only for devnet tests
    default=None,
    help="[DEVNET ONLY] Set specific GENESIS_FORK_VERSION value",
    param_decls='--devnet_chain_setting',
)
@click.pass_context
def generate_bls_to_execution_change(
        ctx: click.Context,
        bls_to_execution_changes_folder: str,
        chain: str,
        mnemonic: str,
        mnemonic_password: str,
        validator_start_index: int,
        validator_index: int,
        bls_withdrawal_credentials: bytes,
        execution_address: HexAddress,
        devnet_chain_setting: dict,
        **kwargs: Any) -> None:
    # Generate folder
    bls_to_execution_changes_folder = os.path.join(
        bls_to_execution_changes_folder,
        DEFAULT_BLS_TO_EXECUTION_CHANGES_FOLDER_NAME,
    )
    if not os.path.exists(bls_to_execution_changes_folder):
        os.mkdir(bls_to_execution_changes_folder)

    # Get chain setting
    chain_setting = get_chain_setting(chain)

    if devnet_chain_setting is not None:
        click.echo('\n%s\n' % '**[Warning] Using devnet chain setting to generate the SignedBLSToExecutionChange.**\t')
        devnet_chain_setting_dict = json.loads(devnet_chain_setting)
        chain_setting = get_devnet_chain_setting(
            network_name=devnet_chain_setting_dict['network_name'],
            genesis_fork_version=devnet_chain_setting_dict['genesis_fork_version'],
            genesis_validator_root=devnet_chain_setting_dict['genesis_validator_root'],
        )

    # TODO: generate multiple?
    num_validators = 1
    amounts = [MAX_DEPOSIT_AMOUNT] * num_validators

    credentials = CredentialList.from_mnemonic(
        mnemonic=mnemonic,
        mnemonic_password=mnemonic_password,
        num_keys=num_validators,
        amounts=amounts,
        chain_setting=chain_setting,
        start_index=validator_start_index,
        hex_eth1_withdrawal_address=execution_address,
    )

    if len(credentials.credentials) != 1:
        raise ValueError(f"It should only generate one credential, but get {len(credentials.credentials)}.")

    # Check if the given old bls_withdrawal_credentials is as same as the mnemonic generated
    validate_bls_withdrawal_credentials_matching(bls_withdrawal_credentials, credentials.credentials[0])

    btec_file = credentials.export_bls_to_execution_change_json(bls_to_execution_changes_folder, validator_index)

    if not verify_bls_to_execution_change_json(btec_file, credentials.credentials):
        raise ValidationError(load_text(['err_verify_btec']))

    click.pause(load_text(['msg_pause']))
