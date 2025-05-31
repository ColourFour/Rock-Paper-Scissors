let humanScore = 0;
let computerScore = 0;
let computerNumber = 1;
let computerChoice = "rock";
let humanCalculate = 0;
let humanChoice = "rock";


function getComputerChoice(){
    computerNumber = Math.random();
    if (computerNumber < 0.33) {
        chomputerChoice = "rock";
    }

    else if (computerNumber > 0.66) {
        computerChoice = "paper";
    }

    else{
        computerChoice = "scissors";
    }
}

function getHumanChoice(){
    let humanCalculate = parseInt(prompt("Please enter 1 = rock, 2 = scissor, 3 = paper."));
    if (humanCalculate == 2){
        humanChoice = "scissors"; 
    }
    else if(humanCalculate == 3){
        humanChoice = "paper";
    }

    else{
        humanChoice = "rock";
    }
}

function playRound(humanChoice, computerChoice){
    let humanCalculate = humanCalculate/3;
}

getComputerChoice();
getHumanChoice();

console.log(computerChoice);
console.log(humanChoice);